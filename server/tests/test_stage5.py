import asyncio
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import make_engine
from app.integrations.agents.contracts import (
    AgentInvocationRequest, AgentInvocationResponse, InvoiceExtractionOutput,
    MaterialReviewOutput, ReconciliationAgentOutput,
)
from app.integrations.agents.fake_gateway import FakeAgentGateway, FakeResult
from app.models import AgentRun, AgentTask, AuditLog, WorkflowEvent
from app.schemas.agent import AgentTaskCreate
from app.services import agent_service
from test_stage2 import create_order, exercise


def reception_task(order_id: str, key: str = "reception-1") -> AgentTaskCreate:
    return AgentTaskCreate(
        order_id=order_id, agent_role="customer_reception", task_type="customer_reception",
        input_schema_version="1.0", idempotency_key=key, correlation_id="corr-1",
        input_payload={"order_id": order_id, "customer_message": "Please check October", "submitted_file_ids": []},
    )


def reception_output() -> dict:
    return {"needs_summary": "October bookkeeping", "material_reminders": ["Upload invoice"],
            "follow_up_questions": []}


def test_agent_request_construction_and_business_contracts():
    payload = reception_task("order-1")
    request = AgentInvocationRequest(
        task_id="task-1", run_id="run-1", order_id=payload.order_id,
        agent_role=payload.agent_role, task_type=payload.task_type,
        input_schema_version=payload.input_schema_version,
        idempotency_key=payload.idempotency_key, correlation_id=payload.correlation_id,
        input_payload=payload.input_payload,
    )
    assert request.input_payload["customer_message"] == "Please check October"
    with pytest.raises(ValidationError):
        AgentInvocationRequest.model_validate({**request.model_dump(), "agent_role": "material_review"})
    with pytest.raises(ValidationError):
        AgentInvocationRequest.model_validate({**request.model_dump(), "input_schema_version": "2.0"})
    with pytest.raises(ValidationError):
        AgentInvocationRequest.model_validate({**request.model_dump(), "input_payload": {**request.input_payload, "order_id": "other"}})
    assert MaterialReviewOutput(file_id="file", review_status="ACCEPTED", is_invoice=True,
                                confidence=0.9).review_status == "ACCEPTED"
    with pytest.raises(ValidationError):
        MaterialReviewOutput(file_id="file", review_status="MAYBE", is_invoice=True, confidence=0.9)
    assert InvoiceExtractionOutput(file_id="file", amount="12.34", confidence=0.8,
                                   extraction_status="ready").amount == "12.34"
    with pytest.raises(ValidationError):
        ReconciliationAgentOutput(narrative_summary="Summary", matched_count=99)


@pytest.mark.parametrize("role,task_type,input_payload", [
    ("material_review", "material_review", {"order_id": "o", "file_id": "f", "file_category": "invoice_image", "mime_type": "image/png"}),
    ("invoice_processing", "invoice_extraction", {"order_id": "o", "file_id": "f", "mime_type": "image/png"}),
    ("data_reconciliation", "reconciliation_summary", {
        "order_id": "o", "financial_summary": {"income_total_cents": 100, "expense_total_cents": 20,
                                               "net_cash_change_cents": 80},
        "reconciliation_result": {"batch_id": "b", "matched_count": 1, "unmatched_count": 0,
                                  "exception_count": 0},
    }),
    ("risk_delivery", "risk_analysis", {"order_id": "o", "exception_id": "e",
                                         "exception_type": "AMOUNT_MISMATCH", "evidence": {},
                                         "related_amount": 100, "difference": 1}),
    ("risk_delivery", "report_draft", {
        "order_id": "o", "report_version": 1,
        "financial_summary": {"income_total_cents": 100, "expense_total_cents": 20,
                              "net_cash_change_cents": 80},
        "reconciliation_summary": {"batch_id": "b", "matched_count": 1, "unmatched_count": 0,
                                   "exception_count": 0},
    }),
])
def test_each_agent_role_has_structured_input(role, task_type, input_payload):
    request = AgentInvocationRequest(task_id="t", run_id="r", order_id="o", agent_role=role,
                                     task_type=task_type, input_schema_version="1.0",
                                     idempotency_key="key", correlation_id="corr", input_payload=input_payload)
    assert request.agent_role == role
    if role == "data_reconciliation":
        with pytest.raises(ValidationError):
            AgentInvocationRequest.model_validate({**request.model_dump(), "input_payload": {
                **input_payload, "financial_summary": {**input_payload["financial_summary"],
                                                         "income_total_cents": 100.0}}})


def test_agent_response_validation():
    now = datetime.now(timezone.utc)
    valid = AgentInvocationResponse(task_id="task", status="succeeded", output_payload=reception_output(),
                                    started_at=now, finished_at=now)
    assert valid.status == "succeeded"
    with pytest.raises(ValidationError):
        AgentInvocationResponse(task_id="task", status="succeeded", started_at=now, finished_at=now)
    with pytest.raises(ValidationError):
        AgentInvocationResponse(task_id="task", status="failed", started_at=now, finished_at=now)
    with pytest.raises(ValidationError):
        AgentInvocationResponse(task_id="task", status="paused", started_at=now.replace(tzinfo=None))


def test_fake_gateway_success_failure_pause_and_production_guard(monkeypatch):
    request_data = reception_task("order-1")
    request = AgentInvocationRequest(task_id="task", run_id="run", **request_data.model_dump())
    fake = FakeAgentGateway({"customer_reception": FakeResult("succeeded", reception_output())})
    assert asyncio.run(fake.invoke(request)).status == "succeeded"
    fake.results["customer_reception"] = FakeResult("failed", error="provider unavailable")
    assert asyncio.run(fake.invoke(request)).error == "provider unavailable"
    fake.results["customer_reception"] = FakeResult("paused")
    assert asyncio.run(fake.invoke(request)).finished_at is None
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="disabled in production"):
            asyncio.run(fake.invoke(request))
    finally:
        monkeypatch.delenv("ENVIRONMENT")
        get_settings.cache_clear()


def test_task_state_idempotency_checkpoint_and_event_stream(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                data = reception_task(order_id)
                task = await agent_service.create_task(session, data)
                task_id, run_id = task.id, task.run_id
                assert task.status == "queued" and task.attempt_count == 0
                again = await agent_service.create_task(session, data)
                assert again.id == task_id
                with pytest.raises(AppError) as conflict:
                    await agent_service.create_task(session, data.model_copy(update={"input_payload": {
                        "order_id": order_id, "customer_message": "Different", "submitted_file_ids": []}}))
                assert conflict.value.code == "idempotency_conflict"
                task = await agent_service.start_task(session, task_id)
                assert task.status == "running" and task.attempt_count == 1
                run = await agent_service.save_checkpoint(session, run_id, {"cursor": 4, "stage": "waiting"})
                assert run.checkpoint_data == {"cursor": 4, "stage": "waiting"}
                assert (await agent_service.pause_task(session, task_id)).status == "paused"
                assert (await agent_service.resume_task(session, task_id)).attempt_count == 2
                completed = await agent_service.complete_task(session, task_id, reception_output(), {"provider": "fake"})
                assert completed.status == "succeeded" and completed.ended_at is not None
                with pytest.raises(AppError):
                    await agent_service.start_task(session, task_id)
            async with sessions() as session:
                saved_task = await session.get(AgentTask, task_id)
                saved_run = await session.get(AgentRun, run_id)
                assert saved_task.output_data == reception_output()
                assert saved_task.provider_metadata == {"provider": "fake"}
                assert saved_run.status == "succeeded" and saved_run.checkpoint_data["cursor"] == 4
                assert saved_run.output_data == reception_output()
                events = (await session.scalars(select(WorkflowEvent).where(WorkflowEvent.order_id == order_id)
                                               .order_by(WorkflowEvent.id))).all()
                assert [event.event_type for event in events] == [
                    "agent.task.queued", "agent.task.running", "agent.run.checkpoint_saved",
                    "agent.task.paused", "agent.task.running", "agent.task.succeeded",
                ]
                assert all(event.order_id == order_id and event.run_id == run_id for event in events)
                assert len((await session.scalars(select(AuditLog).where(AuditLog.entity_id == task_id))).all()) == 5
            alice = {"X-User-Id": "alice"}
            response = await client.get(f"/api/v1/orders/{order_id}/events/stream?follow=false", headers=alice)
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            frames = [part for part in response.text.split("\n\n") if part]
            assert len(frames) == 6
            first_id = int(frames[0].splitlines()[0].removeprefix("id: "))
            last_payload = json.loads(frames[-1].split("data: ", 1)[1])
            assert last_payload["task_id"] == task_id
            assert last_payload["event_type"] == "agent.task.succeeded"
            resumed = await client.get(f"/api/v1/orders/{order_id}/events/stream?follow=false",
                                       headers={**alice, "Last-Event-ID": str(first_id)})
            assert resumed.status_code == 200
            assert len([part for part in resumed.text.split("\n\n") if part]) == 5
            assert (await client.get(f"/api/v1/orders/{order_id}/events/stream?follow=false&after_id={events[-1].id}",
                                     headers=alice)).text == ""
            assert (await client.get(f"/api/v1/orders/{order_id}/events/stream?follow=false",
                                     headers={"X-User-Id": "bob"})).status_code == 404
            assert (await client.get(f"/api/v1/orders/{order_id}/events/stream?follow=false",
                                     headers={**alice, "Last-Event-ID": "bad"})).status_code == 422
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_gateway_invocation_persists_success_failure_and_pause(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                success_task = await agent_service.create_task(session, reception_task(order_id, "success"))
                success_fake = FakeAgentGateway({"customer_reception": FakeResult("succeeded", reception_output())})
                completed = await agent_service.invoke_task(session, success_task.id, success_fake)
                assert completed.status == "succeeded"
                assert len(success_fake.requests) == 1
                assert (await agent_service.invoke_task(session, success_task.id, success_fake)).id == completed.id
                assert len(success_fake.requests) == 1

                failed_task = await agent_service.create_task(session, reception_task(order_id, "failure"))
                failed_fake = FakeAgentGateway({"customer_reception": FakeResult("failed", error="simulated failure")})
                failed = await agent_service.invoke_task(session, failed_task.id, failed_fake)
                assert failed.status == "failed" and failed.error_message == "simulated failure"

                paused_task = await agent_service.create_task(session, reception_task(order_id, "pause"))
                paused_fake = FakeAgentGateway({"customer_reception": FakeResult("paused")})
                paused = await agent_service.invoke_task(session, paused_task.id, paused_fake)
                assert paused.status == "paused" and paused.ended_at is None
                paused_fake.results["customer_reception"] = FakeResult("succeeded", reception_output())
                resumed = await agent_service.invoke_task(session, paused_task.id, paused_fake)
                assert resumed.status == "succeeded" and resumed.attempt_count == 2

                invalid_task = await agent_service.create_task(session, reception_task(order_id, "invalid"))
                invalid_fake = FakeAgentGateway({"customer_reception": FakeResult("succeeded", {"matched_count": 999})})
                invalid = await agent_service.invoke_task(session, invalid_task.id, invalid_fake)
                assert invalid.status == "failed" and invalid.output_data is None
                assert "invalid_agent_output" in invalid.error_message

                class BrokenGateway:
                    async def invoke(self, _request):
                        raise ConnectionError("provider disconnected")

                broken_task = await agent_service.create_task(session, reception_task(order_id, "disconnected"))
                broken = await agent_service.invoke_task(session, broken_task.id, BrokenGateway())
                assert broken.status == "failed" and "provider disconnected" in broken.error_message
            async with sessions() as session:
                runs = (await session.scalars(select(AgentRun).where(AgentRun.order_id == order_id))).all()
                assert len(runs) == 5
                assert sorted(run.status for run in runs) == ["failed", "failed", "failed", "succeeded", "succeeded"]
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_reconciliation_agent_inputs_are_checked_against_backend_batch(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        result = await client.post(f"/api/v1/orders/{order_id}/reconciliation/run",
                                   headers={"X-User-Id": "alice"})
        assert result.status_code == 201, result.text
        batch = result.json()
        financial = {name: batch[name] for name in (
            "income_total_cents", "expense_total_cents", "net_cash_change_cents")}
        summary = {name: batch[name] for name in (
            "matched_count", "unmatched_count", "exception_count")}
        summary.update({"batch_id": batch["id"], "match_ids": [], "exception_ids": []})
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                data = AgentTaskCreate(
                    order_id=order_id, agent_role="data_reconciliation",
                    task_type="reconciliation_summary", idempotency_key="summary-1",
                    correlation_id="corr-1", input_payload={
                        "order_id": order_id, "financial_summary": financial,
                        "reconciliation_result": summary,
                    },
                )
                assert (await agent_service.create_task(session, data)).status == "queued"
                changed = data.model_copy(update={"idempotency_key": "summary-2", "input_payload": {
                    **data.input_payload,
                    "financial_summary": {"income_total_cents": 1, "expense_total_cents": 0,
                                          "net_cash_change_cents": 1},
                }})
                with pytest.raises(AppError) as error:
                    await agent_service.create_task(session, changed)
                assert error.value.code == "invalid_agent_source"
                report = AgentTaskCreate(
                    order_id=order_id, agent_role="risk_delivery", task_type="report_draft",
                    idempotency_key="report-1", correlation_id="corr-1", input_payload={
                        "order_id": order_id, "report_version": 1, "financial_summary": financial,
                        "reconciliation_summary": summary, "exception_summary": [],
                    },
                )
                assert (await agent_service.create_task(session, report)).status == "queued"
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)
