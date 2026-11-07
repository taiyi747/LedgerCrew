"""Authorized full MAF workflow creation, human replies and report finalization."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import HumanReply, ReviewRequest
from app.agents.errors import StaleReviewError
from app.agents.workflow import validate_reply
from app.core.exceptions import AppError
from app.core.security import Principal, assert_owner
from app.integrations.agents.workflow_backend import order_snapshot, snapshot_fingerprint
from app.models import AgentRun, AgentTask, AuditLog
from app.repositories import agents as agent_repo
from app.schemas.agent import AgentTaskCreate
from app.schemas.workflow import WorkflowReplyCreate
from app.services import agent_service, report_service
from app.services.access import order_for_user


async def create(session: AsyncSession, order_id: str, idempotency_key: str,
                 principal: Principal) -> AgentTask:
    order = await order_for_user(session, order_id, principal)
    existing = await agent_repo.task_by_idempotency(session, order_id, idempotency_key)
    if existing is not None:
        if existing.task_type != "full_workflow" or existing.agent_name != "supervisor":
            raise AppError("idempotency_conflict", "Key belongs to another task", 409)
        return existing
    if order.status not in {"ready_to_process", "failed"}:
        raise AppError("workflow_not_ready", "Order materials are not ready", 409)
    try:
        snapshot = await order_snapshot(session, order_id)
    except (ValueError, StaleReviewError) as exc:
        raise AppError("workflow_not_ready", str(exc), 409) from exc
    return await agent_service.create_task(session, AgentTaskCreate(
        order_id=order_id, agent_role="supervisor", task_type="full_workflow",
        idempotency_key=idempotency_key, correlation_id=idempotency_key,
        input_payload={"order_id": order_id, "input_fingerprint": snapshot_fingerprint(snapshot),
                       "revision": 1}))


async def pending_review(session: AsyncSession, task_id: str,
                         principal: Principal) -> dict:
    assert_owner(principal)
    task = await session.get(AgentTask, task_id)
    if task is None or task.task_type != "full_workflow":
        raise AppError("not_found", "Workflow task not found", 404)
    await order_for_user(session, task.order_id, principal)
    run = await session.get(AgentRun, task.run_id)
    data = run.checkpoint_data or {}
    if task.status != "paused" or not data.get("review_request"):
        raise AppError("workflow_not_paused", "Workflow has no pending review", 409)
    return {"task_id": task.id, "request": data["review_request"],
            "report_id": data.get("report_id")}


async def submit_reply(session: AsyncSession, task_id: str, data: WorkflowReplyCreate,
                       principal: Principal) -> AgentTask:
    pending = await pending_review(session, task_id, principal)
    task = await session.get(AgentTask, task_id)
    run = await session.get(AgentRun, task.run_id)
    checkpoint = dict(run.checkpoint_data)
    if checkpoint.get("reply") is not None:
        raise AppError("workflow_reply_exists", "Review already submitted", 409)
    request = ReviewRequest.model_validate(pending["request"])
    reply = HumanReply(identity=request.identity, request_id=request.request_id,
                       action=data.action, comment=data.comment,
                       report_version=data.report_version)
    try:
        validate_reply(request, reply)
    except ValueError as exc:
        raise AppError("invalid_workflow_reply", str(exc), 422) from exc
    task = await agent_service._transition(session, task_id, {"paused"}, "retrying", commit=False)
    if request.kind == "delivery" and data.action == "revise_report":
        if not data.comment.strip():
            raise AppError("reason_required", "Revision reason is required", 422)
        await report_service.reject(session, checkpoint["report_id"], principal, data.comment,
                                    from_workflow=True, commit=False)
    checkpoint["reply"] = reply.model_dump(mode="json")
    checkpoint["review_actor_id"] = principal.user_id
    run.checkpoint_data = checkpoint
    session.add(AuditLog(order_id=task.order_id, actor_type="owner", actor_id=principal.user_id,
                         action="workflow.review_submitted", entity_type="agent_task", entity_id=task.id,
                         details={"request_id": request.request_id, "action": data.action}))
    await session.commit()
    return task
