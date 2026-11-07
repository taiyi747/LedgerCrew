"""Persistent Agent task lifecycle and validated gateway invocation."""

from datetime import timedelta
from typing import Any

from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.types import utc_now
from app.integrations.agents.contracts import AgentInvocationRequest, AgentInvocationResponse, contract_for
from app.integrations.agents.gateway import AgentGateway
from app.models import (
    AgentRun,
    AgentTask,
    AgentTaskHistory,
    AuditLog,
    ExceptionTicket,
    Order,
    ReconciliationBatch,
    UploadedFile,
    WorkflowEvent,
)
from app.repositories import agents as repo
from app.repositories import reconciliation as reconciliation_repo
from app.schemas.agent import AgentTaskCreate
from app.services import order_state
from app.services.material_review import accepted_invoice_review

CHECKPOINT_ADAPTER = TypeAdapter(dict[str, JsonValue])


def _event(session: AsyncSession, task: AgentTask, event_type: str, payload: dict[str, Any] | None = None) -> None:
    session.add(WorkflowEvent(order_id=task.order_id, run_id=task.run_id, task_id=task.id,
                              event_type=event_type, payload=payload))
    session.add(AuditLog(order_id=task.order_id, actor_type="system", actor_id=None,
                         action=event_type, entity_type="agent_task", entity_id=task.id,
                         details=payload))


def _same_request(task: AgentTask, data: AgentTaskCreate) -> bool:
    return (task.agent_name == data.agent_role and task.task_type == data.task_type
            and task.input_schema_version == data.input_schema_version
            and task.correlation_id == data.correlation_id and task.input_data == data.input_payload)


async def _validate_references(session: AsyncSession, data: AgentTaskCreate) -> None:
    if data.task_type == "customer_reception":
        for file_id in data.input_payload.get("submitted_file_ids", []):
            source = await session.get(UploadedFile, file_id)
            if source is None or source.order_id != data.order_id:
                raise AppError("invalid_agent_source", "Submitted file must belong to the task order", 422)
    if data.task_type == "full_workflow":
        from app.integrations.agents.workflow_backend import order_snapshot, snapshot_fingerprint

        snapshot = await order_snapshot(session, data.order_id)
        if snapshot_fingerprint(snapshot) != data.input_payload["input_fingerprint"]:
            raise AppError("stale_workflow_input", "Order materials changed before task creation", 409)
        active = await session.scalar(select(AgentTask.id).where(
            AgentTask.order_id == data.order_id, AgentTask.task_type == "full_workflow",
            AgentTask.status.in_(("queued", "running", "paused", "retrying"))))
        if active is not None:
            raise AppError("workflow_already_active", "Order already has an active workflow", 409)
    if data.task_type in {"material_review", "invoice_extraction"}:
        source = await session.get(UploadedFile, data.input_payload["file_id"])
        if source is None or source.order_id != data.order_id:
            raise AppError("invalid_agent_source", "File must belong to the task order", 422)
        if data.input_payload["mime_type"] != source.mime_type:
            raise AppError("invalid_agent_source", "File MIME type does not match stored metadata", 422)
        if data.task_type == "material_review" and data.input_payload["file_category"] != source.file_category:
            raise AppError("invalid_agent_source", "File category does not match stored metadata", 422)
        if data.task_type == "invoice_extraction" and (source.file_category != "invoice_image" or source.validation_status != "valid"):
            raise AppError("invalid_agent_source", "Invoice extraction requires a validated invoice image", 422)
        if data.task_type == "invoice_extraction":
            await accepted_invoice_review(session, data.order_id, source.id)
    if data.task_type == "risk_analysis":
        payload = data.input_payload
        ticket = await session.get(ExceptionTicket, payload["exception_id"])
        if (ticket is None or ticket.order_id != data.order_id or
                ticket.exception_type != payload["exception_type"] or
                ticket.evidence_json != payload["evidence"] or
                ticket.related_amount_cents != payload.get("related_amount") or
                ticket.difference_cents != payload.get("difference")):
            raise AppError("invalid_agent_source", "Risk input must match a ticket in this order", 422)
    if data.task_type in {"reconciliation_summary", "report_draft"}:
        payload = data.input_payload
        summary = payload["reconciliation_result" if data.task_type == "reconciliation_summary" else "reconciliation_summary"]
        batch = await session.get(ReconciliationBatch, summary["batch_id"])
        financial = payload["financial_summary"]
        if (batch is None or batch.order_id != data.order_id or
            any(financial[name] != getattr(batch, name) for name in (
                "income_total_cents", "expense_total_cents", "net_cash_change_cents")) or
            any(summary[name] != getattr(batch, name) for name in (
                "matched_count", "unmatched_count", "exception_count"))):
            raise AppError("invalid_agent_source", "Summary must match a reconciliation batch in this order", 422)
        matches = await reconciliation_repo.list_matches(session, batch.id)
        tickets = await reconciliation_repo.list_tickets(session, batch.id)
        match_ids = summary.get("match_ids", [])
        exception_ids = summary.get("exception_ids", [])
        if (len(match_ids) != len(matches) or set(match_ids) != {item.id for item in matches} or
                len(exception_ids) != len(tickets) or set(exception_ids) != {item.id for item in tickets}):
            raise AppError("invalid_agent_source", "Summary references must match the reconciliation batch", 422)
        if data.task_type == "report_draft":
            reported = {item["exception_id"]: item for item in payload.get("exception_summary", [])}
            if len(reported) != len(tickets) or any(
                ticket.id not in reported or
                reported[ticket.id]["exception_type"] != ticket.exception_type or
                reported[ticket.id]["status"] != ticket.status or
                reported[ticket.id].get("related_amount_cents") != ticket.related_amount_cents or
                reported[ticket.id].get("difference_cents") != ticket.difference_cents
                for ticket in tickets
            ):
                raise AppError("invalid_agent_source", "Exception summary must match the reconciliation batch", 422)


async def create_task(session: AsyncSession, data: AgentTaskCreate) -> AgentTask:
    existing = await repo.task_by_idempotency(session, data.order_id, data.idempotency_key)
    if existing is not None:
        if not _same_request(existing, data):
            raise AppError("idempotency_conflict", "Idempotency key was used with different task data", 409)
        return existing
    if await session.get(Order, data.order_id) is None:
        raise AppError("not_found", "Order not found", 404)
    await _validate_references(session, data)
    try:
        run = AgentRun(order_id=data.order_id, agent_name=data.agent_role, task_type=data.task_type,
                       input_schema_version=data.input_schema_version, idempotency_key=data.idempotency_key,
                       correlation_id=data.correlation_id, status="queued", input_data=data.input_payload)
        session.add(run)
        await session.flush()
        task = AgentTask(order_id=data.order_id, run_id=run.id, task_key=data.idempotency_key,
                         idempotency_key=data.idempotency_key, correlation_id=data.correlation_id,
                         input_schema_version=data.input_schema_version, agent_name=data.agent_role,
                         task_type=data.task_type, status="queued", input_data=data.input_payload)
        session.add(task)
        await session.flush()
        session.add(AgentTaskHistory(task_id=task.id, from_status=None, to_status="queued", reason="created"))
        _event(session, task, "agent.task.queued", {"agent_role": data.agent_role, "task_type": data.task_type})
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await repo.task_by_idempotency(session, data.order_id, data.idempotency_key)
        if existing is None:
            raise
        if not _same_request(existing, data):
            raise AppError("idempotency_conflict", "Idempotency key was used with different task data", 409) from exc
        return existing
    return task


async def _load(session: AsyncSession, task_id: str) -> tuple[AgentTask, AgentRun]:
    task = await repo.task_by_id(session, task_id)
    if task is None:
        raise AppError("not_found", "Agent task not found", 404)
    run = await repo.run_by_id(session, task.run_id)
    if run is None:
        raise RuntimeError("Agent task has no run")
    return task, run


async def _transition(session: AsyncSession, task_id: str, expected: set[str], target: str,
                      *, output: dict[str, JsonValue] | None = None, error: str | None = None,
                      metadata: dict[str, JsonValue] | None = None,
                      commit: bool = True) -> AgentTask:
    task, run = await _load(session, task_id)
    await session.refresh(task)
    await session.refresh(run)
    if task.status not in expected:
        raise AppError("invalid_task_transition", f"Cannot change task from {task.status} to {target}", 409)
    previous = task.status
    task.status = run.status = target
    now = utc_now()
    if target == "running":
        task.attempt_count += 1
        task.started_at = run.started_at = now
        task.ended_at = run.ended_at = None
        task.error_message = run.error_message = None
        task.next_attempt_at = None
        if task.task_type in {"material_review", "invoice_extraction", "reconciliation_summary", "risk_analysis", "report_draft"}:
            await order_state.begin_processing(session, task.order_id)
    if target in {"succeeded", "failed", "cancelled", "timeout"}:
        task.ended_at = run.ended_at = now
    if target in {"succeeded", "failed", "cancelled", "timeout", "paused"}:
        task.lease_owner = None
        task.lease_expires_at = None
    if target in {"failed", "cancelled", "timeout"}:
        order = await session.get(Order, task.order_id)
        if (task.task_type == "full_workflow" and target in {"failed", "cancelled"}
                and order.status == "awaiting_owner_review"):
            from app.models import ReportVersion

            for report in (await session.scalars(select(ReportVersion).where(
                ReportVersion.workflow_task_id == task.id,
                ReportVersion.status.in_(("draft", "in_review"))))).all():
                report.status = "superseded"
            await order_state.move(session, task.order_id, "processing", "workflow_review_abandoned")
        if order.status == "processing":
            await order_state.move(session, task.order_id, "failed", f"agent_task_{target}")
    if output is not None:
        task.output_data = run.output_data = output
        if task.task_type == "material_review" and output.get("review_status") in {"REJECTED", "NEEDS_REUPLOAD"}:
            await order_state.request_customer(session, task.order_id)
        if task.task_type == "full_workflow" and target == "succeeded":
            from app.services import report_service

            await report_service.approve_workflow_in_transaction(session, task, run, output)
    if error is not None:
        task.error_message = run.error_message = error
    elif target == "timeout":
        task.error_message = run.error_message = "worker_timeout"
    if metadata is not None:
        task.provider_metadata = metadata
    session.add(AgentTaskHistory(task_id=task.id, from_status=previous, to_status=target,
                                 reason=error or ("worker_timeout" if target == "timeout" else None)))
    _event(session, task, f"agent.task.{target}", {"attempt_count": task.attempt_count,
                                                     "has_error": target == "failed"})
    if commit:
        await session.commit()
    return task


async def start_task(session: AsyncSession, task_id: str) -> AgentTask:
    return await _transition(session, task_id, {"queued", "retrying"}, "running")


async def cancel_task(session: AsyncSession, task_id: str) -> AgentTask:
    task, _ = await _load(session, task_id)
    if task.status == "cancelled":
        return task
    return await _transition(session, task_id, {"queued", "running", "paused", "retrying"}, "cancelled")


async def retry_task(session: AsyncSession, task_id: str) -> AgentTask:
    task, _ = await _load(session, task_id)
    if task.attempt_count >= get_settings().worker_max_attempts:
        raise AppError("retry_limit", "Task retry limit reached", 409)
    return await _transition(session, task_id, {"failed", "timeout"}, "retrying")


async def timeout_stale_tasks(session: AsyncSession) -> list[AgentTask]:
    threshold = utc_now() - timedelta(seconds=get_settings().worker_timeout_seconds)
    stale = (await session.scalars(select(AgentTask).where(AgentTask.status == "running",
        AgentTask.started_at <= threshold,
        or_(AgentTask.lease_owner.is_(None), AgentTask.lease_expires_at <= utc_now())))).all()
    result = []
    for task in stale:
        try:
            result.append(await _transition(session, task.id, {"running"}, "timeout"))
        except AppError as exc:
            if exc.code != "invalid_task_transition":
                raise
    return result


async def pause_task(session: AsyncSession, task_id: str,
                     metadata: dict[str, JsonValue] | None = None) -> AgentTask:
    return await _transition(session, task_id, {"running"}, "paused", metadata=metadata)


async def resume_task(session: AsyncSession, task_id: str) -> AgentTask:
    return await _transition(session, task_id, {"paused"}, "running")


async def complete_task(session: AsyncSession, task_id: str,
                        output_payload: dict[str, JsonValue],
                        metadata: dict[str, JsonValue] | None = None) -> AgentTask:
    task, _ = await _load(session, task_id)
    _, output_model = contract_for(task.agent_name, task.task_type, task.input_schema_version)
    validated = output_model.model_validate(output_payload)
    if task.task_type in {"material_review", "invoice_extraction"} and validated.file_id != task.input_data["file_id"]:
        raise ValueError("Agent output file_id differs from task input")
    if task.task_type == "risk_analysis" and validated.exception_id != task.input_data["exception_id"]:
        raise ValueError("Agent output exception_id differs from task input")
    if task.task_type == "report_draft" and (validated.order_id != task.order_id or
                                             validated.report_version != task.input_data["report_version"]):
        raise ValueError("Agent output report identity differs from task input")
    return await _transition(session, task_id, {"running"}, "succeeded",
                             output=validated.model_dump(mode="json"), metadata=metadata)


async def fail_task(session: AsyncSession, task_id: str, error: str,
                    metadata: dict[str, JsonValue] | None = None) -> AgentTask:
    if not error.strip():
        raise ValueError("Failure reason is required")
    return await _transition(session, task_id, {"queued", "running", "paused"}, "failed",
                             error=error, metadata=metadata)


async def save_checkpoint(session: AsyncSession, run_id: str,
                          checkpoint: dict[str, JsonValue]) -> AgentRun:
    run = await repo.run_by_id(session, run_id)
    if run is None:
        raise AppError("not_found", "Agent run not found", 404)
    if run.status not in {"running", "paused"}:
        raise AppError("invalid_run_state", "Checkpoint requires running or paused run", 409)
    run.checkpoint_data = CHECKPOINT_ADAPTER.validate_python(checkpoint)
    session.add(WorkflowEvent(order_id=run.order_id, run_id=run.id,
                              event_type="agent.run.checkpoint_saved", payload={"run_id": run.id}))
    session.add(AuditLog(order_id=run.order_id, actor_type="system", actor_id=None,
                         action="agent.run.checkpoint_saved", entity_type="agent_run", entity_id=run.id))
    await session.commit()
    return run


async def invoke_task(session: AsyncSession, task_id: str, gateway: AgentGateway,
                      *, lease_owner: str | None = None,
                      lease_generation: int | None = None) -> AgentTask:
    task, _ = await _load(session, task_id)
    if task.status in {"succeeded", "failed", "cancelled", "timeout"}:
        return task  # repeated delivery cannot invoke again
    if get_settings().environment == "production" and lease_owner is None:
        raise AppError("worker_lease_required", "Production Agent execution requires a lease", 409)
    if lease_owner is not None and (task.lease_owner != lease_owner
                                    or task.lease_generation != lease_generation
                                    or task.lease_expires_at is None
                                    or task.lease_expires_at <= utc_now()):
        raise AppError("worker_lease_lost", "Task lease is no longer held", 409)
    if task.status in {"queued", "retrying"}:
        task = await start_task(session, task_id)
    elif task.status == "paused":
        task = await resume_task(session, task_id)
    elif task.status == "running" and lease_owner is not None:
        pass  # A claimed task can resume after start was committed.
    else:
        raise AppError("task_already_running", "Task is already running", 409)
    request = AgentInvocationRequest(
        task_id=task.id, run_id=task.run_id, order_id=task.order_id,
        agent_role=task.agent_name, task_type=task.task_type,
        input_schema_version=task.input_schema_version, idempotency_key=task.idempotency_key,
        correlation_id=task.correlation_id, input_payload=task.input_data,
    )
    try:
        raw_response = await gateway.invoke(request)
        response = AgentInvocationResponse.model_validate(
            raw_response.model_dump() if isinstance(raw_response, BaseModel) else raw_response)
        if response.task_id != task.id:
            raise ValueError("Agent response task_id does not match invocation")
    except Exception as exc:
        await session.refresh(task)
        if task.status in {"cancelled", "timeout"} or (lease_owner is not None and
            (task.lease_owner != lease_owner or task.lease_generation != lease_generation
             or task.lease_expires_at is None or task.lease_expires_at <= utc_now())):
            return task
        return await fail_task(session, task.id, f"agent_invocation_failed: {type(exc).__name__}")
    await session.refresh(task)
    if task.status in {"cancelled", "timeout"} or (lease_owner is not None and
        (task.lease_owner != lease_owner or task.lease_generation != lease_generation
         or task.lease_expires_at is None or task.lease_expires_at <= utc_now())):
        return task
    if response.status == "succeeded":
        try:
            return await complete_task(session, task.id, response.output_payload, response.provider_metadata)
        except (ValueError, ValidationError):
            # Pydantic errors may include the rejected model output (customer data).
            return await fail_task(session, task.id, "invalid_agent_output", response.provider_metadata)
        except AppError as exc:
            await session.rollback()
            return await fail_task(session, task.id, f"workflow_commit_failed: {exc.code}",
                                   response.provider_metadata)
    if response.status == "paused":
        return await pause_task(session, task.id, response.provider_metadata)
    if response.status == "failed":
        return await fail_task(session, task.id, response.error, response.provider_metadata)
    return await fail_task(session, task.id, "invalid_agent_response_status", response.provider_metadata)
