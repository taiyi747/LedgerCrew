from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import Principal, assert_owner
from app.db.types import utc_now
from app.integrations.agents.contracts import contract_for
from app.models import (
    AgentResultReview,
    AgentRun,
    AgentTask,
    AgentTaskHistory,
    AuditLog,
    InvoiceRecord,
    ReportVersion,
    WorkflowEvent,
)
from app.schemas.agent import AgentTaskCreate
from app.schemas.agent_review import AgentReviewCreate, AgentReviewStats
from app.services import agent_service
from app.services.access import order_for_user


async def _task_for_owner(session: AsyncSession, task_id: str, principal: Principal) -> AgentTask:
    assert_owner(principal)
    task = await session.get(AgentTask, task_id)
    if task is None:
        raise AppError("not_found", "Agent task not found", 404)
    await order_for_user(session, task.order_id, principal)
    return task


async def list_reviews(session: AsyncSession, task_id: str, principal: Principal) -> list[AgentResultReview]:
    await _task_for_owner(session, task_id, principal)
    return list((await session.scalars(select(AgentResultReview).where(AgentResultReview.task_id == task_id)
                                       .order_by(AgentResultReview.version))).all())


async def review_result(session: AsyncSession, task_id: str, data: AgentReviewCreate,
                        principal: Principal) -> AgentResultReview:
    task = await _task_for_owner(session, task_id, principal)
    if task.status != "succeeded" or task.output_data is None:
        raise AppError("result_not_reviewable", "A successful Agent result is required", 409)
    note = data.note.strip()
    if not note:
        raise AppError("note_required", "Review note is required", 422)
    if (data.decision == "corrected") != (data.revised_output is not None):
        raise AppError("invalid_review_output", "Corrected review requires revised_output only", 422)
    if data.decision in {"corrected", "rejected"}:
        used = await session.scalar(select(InvoiceRecord.id).where(
            (InvoiceRecord.source_task_id == task.id) | (InvoiceRecord.material_review_task_id == task.id)))
        used_report = await session.scalar(select(ReportVersion.id).where(ReportVersion.source_task_id == task.id))
        if used is not None or used_report is not None:
            raise AppError("result_already_used", "Result has downstream records; create a new analysis", 409)
    original = dict(task.output_data)
    revised = None
    if data.decision == "corrected":
        _, output_model = contract_for(task.agent_name, task.task_type, task.input_schema_version)
        revised = output_model.model_validate(data.revised_output).model_dump(mode="json")
        for identity_field in ("file_id", "order_id", "report_version", "exception_id"):
            if identity_field in original and revised.get(identity_field) != original[identity_field]:
                raise AppError("invalid_review_output", "Result identity cannot change", 422)
        task.output_data = revised
        run = await session.get(AgentRun, task.run_id)
        run.output_data = revised
    elif data.decision == "rejected":
        session.add(AgentTaskHistory(task_id=task.id, from_status=task.status, to_status="failed",
                                     reason="human_rejected"))
        task.status = "failed"
        task.error_message = "human_rejected"
        task.ended_at = utc_now()
        run = await session.get(AgentRun, task.run_id)
        run.status = "failed"
        run.error_message = "human_rejected"
        run.ended_at = task.ended_at
    latest = await session.scalar(select(func.coalesce(func.max(AgentResultReview.version), 0)).where(
        AgentResultReview.task_id == task.id))
    review = AgentResultReview(task_id=task.id, version=latest + 1, decision=data.decision,
                               original_output=original, revised_output=revised, note=note,
                               reviewer_id=principal.user_id)
    session.add(review)
    session.add(AuditLog(order_id=task.order_id, actor_type="owner", actor_id=principal.user_id,
                         action=f"agent.result_{data.decision}", entity_type="agent_task", entity_id=task.id,
                         details={"review_version": review.version}))
    session.add(WorkflowEvent(order_id=task.order_id, run_id=task.run_id, task_id=task.id,
                              event_type=f"agent.result_{data.decision}",
                              payload={"review_version": review.version}))
    await session.commit()
    return review


async def rerun_result(session: AsyncSession, task_id: str, idempotency_key: str,
                       principal: Principal) -> AgentTask:
    task = await _task_for_owner(session, task_id, principal)
    if task.status not in {"succeeded", "failed"}:
        raise AppError("result_not_rerunnable", "Task must be complete before reanalysis", 409)
    data = AgentTaskCreate(order_id=task.order_id, agent_role=task.agent_name,
                           task_type=task.task_type, input_schema_version=task.input_schema_version,
                           idempotency_key=idempotency_key, correlation_id=task.correlation_id or task.id,
                           input_payload=task.input_data)
    return await agent_service.create_task(session, data)


async def review_stats(session: AsyncSession, order_id: str, principal: Principal) -> AgentReviewStats:
    assert_owner(principal)
    await order_for_user(session, order_id, principal)
    rows = (await session.execute(select(AgentResultReview.decision, func.count())
                                  .join(AgentTask, AgentResultReview.task_id == AgentTask.id)
                                  .where(AgentTask.order_id == order_id)
                                  .group_by(AgentResultReview.decision))).all()
    counts = dict(rows)
    reviewed_tasks = await session.scalar(select(func.count(func.distinct(AgentResultReview.task_id)))
                                          .join(AgentTask, AgentResultReview.task_id == AgentTask.id)
                                          .where(AgentTask.order_id == order_id))
    return AgentReviewStats(confirmed=counts.get("confirmed", 0), corrected=counts.get("corrected", 0),
                            rejected=counts.get("rejected", 0), reviewed_tasks=reviewed_tasks or 0)
