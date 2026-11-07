from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import Principal
from app.models import AuditLog, ExceptionTicket, InvoiceRecord, ReconciliationBatch, ReconciliationMatch, Studio, WorkflowEvent
from app.repositories import reconciliation as repo
from app.schemas.reconciliation import InvoiceRecordCreate
from app.services.access import order_for_user
from app.services.reconciliation_engine import InvoiceInput, MATCH_RULE, TransactionInput, reconcile


async def persist_invoice(session: AsyncSession, order_id: str, data: InvoiceRecordCreate) -> InvoiceRecord:
    """Future Agent adapter calls this after authorization; never mutates the source file."""
    from app.models import UploadedFile

    source = await session.get(UploadedFile, data.source_file_id)
    if source is None or source.order_id != order_id or source.file_category != "invoice_image" or source.validation_status != "valid":
        raise AppError("invalid_invoice_source", "A validated invoice image from this order is required", 422)
    invoice = InvoiceRecord(order_id=order_id, **data.model_dump())
    session.add(invoice)
    await session.flush()
    session.add(AuditLog(order_id=order_id, actor_type="agent_adapter", actor_id=None,
                         action="invoice.persisted", entity_type="invoice_record", entity_id=invoice.id,
                         details={"source_file_id": source.id}))
    return invoice


async def run(session: AsyncSession, order_id: str, principal: Principal, *, delegated_run_id: str | None = None) -> ReconciliationBatch:
    order = await order_for_user(session, order_id, principal)
    from app.live.service import current_run
    live = await current_run(session, order_id)
    if live and delegated_run_id != live.id:
        raise AppError("supervisor_required", "当前订单的对账必须由总管委派给数据核对 Agent。", 409)
    studio = await session.get(Studio, order.studio_id)
    invoices = await repo.list_invoices(session, order_id)
    transactions = await repo.list_transactions(session, order_id)
    hashes = await repo.invoice_file_hashes(session, order_id)
    result = reconcile(
        studio.name, order.period_start, order.period_end,
        [InvoiceInput(item.id, item.invoice_number, item.issue_date, item.seller, item.buyer,
                      item.total_amount_cents, item.extraction_status, hashes.get(item.source_file_id))
         for item in invoices],
        [TransactionInput(item.id, item.external_id, item.transaction_date, item.normalized_counterparty,
                          item.direction, item.amount_cents, item.description) for item in transactions],
    )
    batch = ReconciliationBatch(
        order_id=order_id, batch_number=await repo.next_batch_number(session, order_id),
        income_total_cents=result.income_total_cents, expense_total_cents=result.expense_total_cents,
        net_cash_change_cents=result.net_cash_change_cents, matched_count=result.matched_count,
        unmatched_count=result.unmatched_count, exception_count=result.exception_count,
    )
    session.add(batch)
    await session.flush()
    for match in result.matches:
        session.add(ReconciliationMatch(
            order_id=order_id, batch_id=batch.id, invoice_id=match.invoice_id,
            transaction_id=match.transaction_id, match_status="matched", difference_cents=0,
            match_rule=MATCH_RULE, evidence_json=match.evidence_json,
        ))
    for ticket in result.tickets:
        session.add(ExceptionTicket(
            exception_no=f"EX-{uuid4().hex.upper()}", order_id=order_id, batch_id=batch.id,
            exception_type=ticket.exception_type, invoice_id=ticket.invoice_id,
            transaction_id=ticket.transaction_id, related_amount_cents=ticket.related_amount_cents,
            difference_cents=ticket.difference_cents, status="open", evidence_json=ticket.evidence_json,
        ))
    session.add(WorkflowEvent(order_id=order_id, event_type="reconciliation.completed",
                              payload={"batch_id": batch.id, "matched_count": result.matched_count,
                                       "exception_count": result.exception_count}))
    session.add(AuditLog(order_id=order_id, actor_type="customer", actor_id=principal.user_id,
                         action="reconciliation.run", entity_type="reconciliation_batch", entity_id=batch.id,
                         details={"batch_number": batch.batch_number, "matched_count": result.matched_count,
                                  "exception_count": result.exception_count}))
    await session.commit()
    return batch


async def get_latest(session: AsyncSession, order_id: str, principal: Principal) -> ReconciliationBatch:
    await order_for_user(session, order_id, principal)
    batch = await repo.latest_batch(session, order_id)
    if batch is None:
        raise AppError("not_found", "No reconciliation batch exists for this order", 404)
    return batch


async def get_matches(session: AsyncSession, order_id: str, principal: Principal) -> list[ReconciliationMatch]:
    batch = await get_latest(session, order_id, principal)
    return await repo.list_matches(session, batch.id)


async def get_exceptions(session: AsyncSession, order_id: str, principal: Principal) -> list[ExceptionTicket]:
    batch = await get_latest(session, order_id, principal)
    return await repo.list_tickets(session, batch.id)
