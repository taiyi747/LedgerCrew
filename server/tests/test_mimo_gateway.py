"""The backend task boundary reaches MAF and persists request accounting."""

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import create_order, exercise

from app.agents.config import Settings as MiMoSettings
from app.agents.contracts import RunIdentity
from app.agents.errors import RequestBudgetExceeded
from app.agents.runner import MiMoRunner, RequestBudget
from app.core.config import get_settings
from app.db.session import make_engine
from app.integrations.agents.mimo_gateway import MiMoAgentGateway, TaskModelArtifacts
from app.models import AgentModelArtifact
from app.schemas.agent import AgentTaskCreate
from app.services import agent_service
from scripts.run_agent_tasks import run_once


def test_backend_task_calls_mimo_and_persists_budget(tmp_path, monkeypatch) -> None:
    async def scenario(client, storage) -> None:
        _, order_id = await create_order(client)
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={
                "id": "mock-completion", "object": "chat.completion", "created": 1,
                "model": "mimo-v2.6-flash", "choices": [{"index": 0, "message": {
                    "role": "assistant", "content": json.dumps({
                        "needs_summary": "需要整理发票", "material_reminders": [],
                        "follow_up_questions": [],
                    })}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 11, "total_tokens": 20},
            })

        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        mimo_settings = MiMoSettings(api_key=SecretStr("local-test-key"))
        gateway = MiMoAgentGateway(sessions, storage, mimo_settings,
                                   MiMoRunner(mimo_settings, transport=httpx.MockTransport(handler)))
        try:
            async with sessions() as db:
                task = await agent_service.create_task(db, AgentTaskCreate(
                    order_id=order_id, agent_role="customer_reception", task_type="customer_reception",
                    idempotency_key="real-adapter", correlation_id="adapter-test",
                    input_payload={"order_id": order_id, "customer_message": "请处理发票"}))
                assert await run_once(sessions, gateway)
                await db.refresh(task)
                finished = task
                assert finished.status == "succeeded"
                assert finished.output_data["needs_summary"] == "需要整理发票"
                assert finished.provider_metadata["provider"] == "mimo"
                assert finished.provider_metadata["usage"]["total_token_count"] == 20
                assert (await agent_service.invoke_task(db, task.id, gateway)).status == "succeeded"
                assert not await run_once(sessions, gateway)
                assert len(requests) == 1
                artifacts = (await db.scalars(select(AgentModelArtifact).where(
                    AgentModelArtifact.task_id == task.id))).all()
                assert {item.kind for item in artifacts} == {
                    "usage", "wire_request", "model_usage", "model_settlement"}
                assert next(item.payload for item in artifacts if item.kind == "usage")["requests"] == 1
                settlement = next(item.payload for item in artifacts if item.kind == "model_settlement")
                assert settlement["usage"] == {
                    "prompt_tokens": 9, "completion_tokens": 11, "total_tokens": 20}
                assert settlement["usage_status"] == "known"
                assert "请处理发票" not in json.dumps([item.payload for item in artifacts], ensure_ascii=False)
                resumed_budget = RequestBudget(
                    TaskModelArtifacts(sessions, task.id),
                    RunIdentity(order_id=order_id, run_id=task.run_id, revision=2), 1)
                with pytest.raises(RequestBudgetExceeded):
                    await resumed_budget.reserve()
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_two_budget_instances_cannot_exceed_one_request(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                task = await agent_service.create_task(db, AgentTaskCreate(
                    order_id=order_id, agent_role="customer_reception", task_type="customer_reception",
                    idempotency_key="atomic-budget", correlation_id="budget-test",
                    input_payload={"order_id": order_id, "customer_message": "test"}))
            identity = RunIdentity(order_id=order_id, run_id=task.run_id, revision=1)
            first = RequestBudget(TaskModelArtifacts(sessions, task.id), identity, 1)
            second = RequestBudget(TaskModelArtifacts(sessions, task.id), identity, 1)
            results = await asyncio.gather(first.reserve(), second.reserve(), return_exceptions=True)
            assert sum(isinstance(result, RequestBudgetExceeded) for result in results) == 1
            reservation = next(result for result in results if isinstance(result, str))
            await first.settle(reservation, "http_response", 200, None)
            await second.settle(reservation, "request_failed")
            async with sessions() as db:
                artifacts = (await db.scalars(select(AgentModelArtifact).where(
                    AgentModelArtifact.task_id == task.id))).all()
                assert [item.payload["requests"] for item in artifacts if item.kind == "usage"] == [1]
                settlements = [item for item in artifacts if item.kind == "model_settlement"]
                assert len(settlements) == 1
                assert settlements[0].payload["usage_status"] == "unknown"
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)
