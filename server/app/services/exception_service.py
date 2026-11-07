from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import Principal, assert_owner
from app.models import AuditLog, ExceptionDecision, ExceptionSupplement, ExceptionTicket, WorkflowEvent
from app.repositories import delivery as repo
from app.schemas.agent import AgentTaskCreate
from app.schemas.delivery import ExceptionDecisionCreate
from app.services import agent_service, file_service
from app.services.access import order_for_user
from app.storage.base import Storage


async def get_exception(session: AsyncSession, exception_id: str, principal: Principal) -> ExceptionTicket:
    ticket = await session.get(ExceptionTicket, exception_id)
    if ticket is None:
        raise AppError("not_found", "Exception not found", 404)
    await order_for_user(session, ticket.order_id, principal)
    return ticket


async def add_supplement(
    session: AsyncSession, storage: Storage, exception_id: str, principal: Principal,
    settings: Settings, explanation: str | None, upload: UploadFile | None, existing_file_id: str | None = None, expected_revision: int | None = None,
) -> ExceptionSupplement:
    if principal.role != "customer":
        raise AppError("forbidden", "Customer role is required", 403)
    ticket = await get_exception(session, exception_id, principal)
    from app.live.service import guard_inputs, touch_inputs
    await guard_inputs(session, ticket.order_id, expected_revision)
    if ticket.status in {"resolved", "accepted_unresolved"}:
        raise AppError("exception_closed", "Closed exception cannot receive supplements", 409)
    text = (explanation or "").strip() or None
    if text and len(text) > 5000:
        raise AppError("supplement_too_long", "Explanation exceeds 5000 characters", 422)
    if text is None and upload is None and existing_file_id is None:
        raise AppError("empty_supplement", "Explanation or evidence image is required", 422)
    file = (await file_service.save_supporting_evidence(
        session, storage, ticket.order_id, upload, principal, settings)) if upload is not None else None
    if existing_file_id:
        from app.models import UploadedFile
        file = await session.get(UploadedFile, existing_file_id)
        if upload is not None or not file or file.order_id != ticket.order_id or file.validation_status != "valid" or not file.is_active:
            raise AppError("invalid_supplement_file", "补充附件必须是本订单有效文件。", 422)
    if file is not None:
        await session.flush()
    supplement = ExceptionSupplement(exception_id=ticket.id, order_id=ticket.order_id,
                                     actor_id=principal.user_id, explanation=text,
                                     file_id=file.id if file else None)
    session.add(supplement)
    ticket.status = "waiting_owner"
    await session.flush()
    session.add(AuditLog(order_id=ticket.order_id, actor_type="customer", actor_id=principal.user_id,
                         action="exception.supplemented", entity_type="exception_supplement", entity_id=supplement.id,
                         details={"exception_id": ticket.id, "file_id": supplement.file_id}))
    session.add(WorkflowEvent(order_id=ticket.order_id, event_type="exception.supplemented",
                              payload={"exception_id": ticket.id, "supplement_id": supplement.id}))
    await touch_inputs(session, ticket.order_id, wake=True)
    from app.live.models import OrderMessage
    from app.models import Order
    order = await session.get(Order, ticket.order_id)
    session.add(OrderMessage(order_id=ticket.order_id, role="user", content=text or "已提交补充凭证。",
                            file_ids=[file.id] if file else [], evidence_refs=[ticket.id],
                            input_revision=order.input_revision))
    await session.commit()
    return supplement


async def list_supplements(session: AsyncSession, exception_id: str, principal: Principal) -> list[ExceptionSupplement]:
    await get_exception(session, exception_id, principal)
    return await repo.list_supplements(session, exception_id)


async def decide(session: AsyncSession, exception_id: str, data: ExceptionDecisionCreate,
                 principal: Principal) -> ExceptionDecision:
    assert_owner(principal)
    ticket = await get_exception(session, exception_id, principal)
    from app.live.service import guard_inputs, touch_inputs, current_run
    from app.repositories import reconciliation as reconciliation_repo
    await guard_inputs(session, ticket.order_id)
    live = await current_run(session, ticket.order_id)
    if live:
        from app.models import Order
        order = await session.get(Order, ticket.order_id)
        if data.expected_revision is not None and data.expected_revision != order.input_revision:
            raise AppError("stale_revision", "订单材料或决定已变化，请刷新。", 409)
        latest = await reconciliation_repo.latest_batch(session, ticket.order_id)
        if not latest or latest.id != ticket.batch_id or data.target_version != await repo.next_report_version(session, ticket.order_id):
            raise AppError("stale_decision", "异常批次或目标报告版本已变化，请刷新。", 409)
    if ticket.status in {"resolved", "accepted_unresolved"}:
        raise AppError("exception_closed", "Closed exception cannot receive a new decision", 409)
    before = ticket.business_classification
    if data.decision == "resolve":
        ticket.status = "resolved"
    elif data.decision == "request_supplement":
        ticket.status = "waiting_customer"
    elif data.decision == "reanalyze":
        ticket.status = "open"
    elif data.decision == "correct_classification":
        after = data.classification_after.strip()
        if after == before:
            raise AppError("classification_unchanged", "New classification must differ", 422)
        ticket.business_classification = after
        ticket.status = "waiting_owner"
    elif data.decision == "accept_unresolved":
        ticket.status = "accepted_unresolved"
    decision = ExceptionDecision(
        exception_id=ticket.id, order_id=ticket.order_id, decision=data.decision,
        actor_id=principal.user_id, reason=data.reason.strip(), target_version=data.target_version,
        classification_before=before,
        classification_after=ticket.business_classification if data.decision == "correct_classification" else None,
    )
    session.add(decision)
    await session.flush()
    session.add(AuditLog(order_id=ticket.order_id, actor_type="owner", actor_id=principal.user_id,
                         action="exception.decided", entity_type="exception_decision", entity_id=decision.id,
                         details={"exception_id": ticket.id, "decision": data.decision,
                                  "target_version": data.target_version}))
    session.add(WorkflowEvent(order_id=ticket.order_id,
                              event_type="exception.reanalysis_requested" if data.decision == "reanalyze" else "exception.decided",
                              payload={"exception_id": ticket.id, "decision_id": decision.id,
                                       "status": ticket.status}))
    await touch_inputs(session, ticket.order_id, wake=True,
                       force_wake=data.decision in {"reanalyze", "correct_classification"})
    if data.decision == "request_supplement":
        from app.live.models import OrderMessage
        from app.models import Order
        order = await session.get(Order, ticket.order_id)
        session.add(OrderMessage(order_id=ticket.order_id, role="assistant", content=data.reason,
                                 evidence_refs=[ticket.id], input_revision=order.input_revision))
    if data.decision == "reanalyze" and not live:
        await agent_service.create_task(session, AgentTaskCreate(
            order_id=ticket.order_id, agent_role="risk_delivery", task_type="risk_analysis",
            idempotency_key=f"reanalyze:{decision.id}", correlation_id=decision.id,
            input_payload={
                "order_id": ticket.order_id, "exception_id": ticket.id,
                "exception_type": ticket.exception_type, "evidence": ticket.evidence_json,
                "related_amount": ticket.related_amount_cents,
                "difference": ticket.difference_cents,
            },
        ))
    else:
        await session.commit()
    return decision
