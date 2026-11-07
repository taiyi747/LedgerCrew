from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import Principal, assert_owner
from app.db.types import utc_now
from app.models import AgentRun, AuditLog, CustomerFeedback, FeedbackAction, Order
from app.schemas.feedback import FeedbackActionCreate, FeedbackCreate
from app.services.access import studio_for_user


async def create_feedback(session: AsyncSession, studio_id: str, data: FeedbackCreate,
                          principal: Principal) -> CustomerFeedback:
    await studio_for_user(session, studio_id, principal)
    if data.order_id:
        order = await session.get(Order, data.order_id)
        if order is None or order.studio_id != studio_id:
            raise AppError("not_found", "Order not found", 404)
    if data.run_id:
        run = await session.get(AgentRun, data.run_id)
        if run is None or data.order_id is None or run.order_id != data.order_id:
            raise AppError("not_found", "Workflow run not found", 404)
    feedback = CustomerFeedback(studio_id=studio_id, order_id=data.order_id, run_id=data.run_id,
                                category=data.category, status="open", message=data.message.strip(),
                                submitted_by=principal.user_id)
    session.add(feedback)
    await session.flush()
    session.add(AuditLog(order_id=data.order_id, actor_type="customer", actor_id=principal.user_id,
                         action="feedback.created", entity_type="customer_feedback", entity_id=feedback.id,
                         details={"category": data.category}))
    await session.commit()
    return feedback


async def get_feedback(session: AsyncSession, feedback_id: str, principal: Principal) -> CustomerFeedback:
    feedback = await session.get(CustomerFeedback, feedback_id)
    if feedback is None:
        raise AppError("not_found", "Feedback not found", 404)
    await studio_for_user(session, feedback.studio_id, principal)
    return feedback


async def list_feedback(session: AsyncSession, studio_id: str, principal: Principal) -> list[CustomerFeedback]:
    await studio_for_user(session, studio_id, principal)
    return list((await session.scalars(select(CustomerFeedback).where(CustomerFeedback.studio_id == studio_id)
                                       .order_by(CustomerFeedback.created_at.desc()))).all())


async def list_actions(session: AsyncSession, feedback_id: str, principal: Principal) -> list[FeedbackAction]:
    await get_feedback(session, feedback_id, principal)
    return list((await session.scalars(select(FeedbackAction).where(FeedbackAction.feedback_id == feedback_id)
                                       .order_by(FeedbackAction.created_at))).all())


async def handle_feedback(session: AsyncSession, feedback_id: str, data: FeedbackActionCreate,
                          principal: Principal) -> CustomerFeedback:
    assert_owner(principal)
    feedback = await get_feedback(session, feedback_id, principal)
    if feedback.status not in {"open", "in_progress"} or feedback.status == data.action:
        raise AppError("invalid_feedback_transition", "Feedback transition is invalid", 409)
    note = data.note.strip()
    if not note:
        raise AppError("note_required", "Handling note is required", 422)
    before = feedback.status
    feedback.status = data.action
    feedback.handled_by = principal.user_id
    feedback.handled_at = utc_now()
    session.add(FeedbackAction(feedback_id=feedback.id, actor_id=principal.user_id,
                               action=data.action, note=note))
    session.add(AuditLog(order_id=feedback.order_id, actor_type="owner", actor_id=principal.user_id,
                         action="feedback.handled", entity_type="customer_feedback", entity_id=feedback.id,
                         details={"from": before, "to": data.action}))
    await session.commit()
    return feedback
