"""Server-owned order lifecycle transitions; never exposed as arbitrary HTTP updates."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models import AuditLog, Order, PaymentIntent, ReportVersion, UploadedFile, WorkflowEvent

ALLOWED: dict[str, set[str]] = {
    "draft": {"awaiting_materials"},
    "awaiting_materials": {"ready_to_process", "awaiting_customer"},
    "ready_to_process": {"processing", "awaiting_customer"},
    "processing": {"awaiting_customer", "awaiting_owner_review", "failed"},
    "awaiting_customer": {"processing"},
    "awaiting_owner_review": {"approved", "processing"},
    "approved": {"delivered", "processing"},
    "delivered": {"processing"},
    "failed": {"processing"},
}


async def move(session: AsyncSession, order_id: str, target: str, reason: str,
               actor_type: str = "system", actor_id: str | None = None) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise AppError("not_found", "Order not found", 404)
    if order.status == target:
        return order
    if target not in ALLOWED[order.status]:
        raise AppError("invalid_order_transition", f"Cannot change order from {order.status} to {target}", 409)
    previous = order.status
    order.status = target
    details = {"from": previous, "to": target, "reason": reason}
    session.add(AuditLog(order_id=order_id, actor_type=actor_type, actor_id=actor_id,
                         action="order.status_changed", entity_type="order", entity_id=order_id,
                         details=details))
    session.add(WorkflowEvent(order_id=order_id, event_type="order.status_changed", payload=details))
    return order


async def refresh_materials(session: AsyncSession, order_id: str) -> Order:
    order = await session.get(Order, order_id)
    if order.status == "draft":
        await move(session, order_id, "awaiting_materials", "material_upload_started")
    if order.status == "awaiting_materials":
        categories = set((await session.scalars(select(UploadedFile.file_category).where(
            UploadedFile.order_id == order_id, UploadedFile.validation_status == "valid"))).all())
        if {"invoice_image", "bank_statement_csv"} <= categories:
            await move(session, order_id, "ready_to_process", "required_material_categories_present")
    return order


async def begin_processing(session: AsyncSession, order_id: str) -> Order:
    order = await session.get(Order, order_id)
    if order.status in {"ready_to_process", "awaiting_customer", "approved", "delivered", "failed"}:
        await move(session, order_id, "processing", "processing_started")
    return order


async def request_customer(session: AsyncSession, order_id: str) -> Order:
    order = await session.get(Order, order_id)
    if order.status in {"awaiting_materials", "ready_to_process", "processing"}:
        await move(session, order_id, "awaiting_customer", "supplement_requested")
    return order


async def deliver_published_report(session: AsyncSession, report_id: str, actor_id: str) -> Order:
    """Deliver only a published version whose configured charge has succeeded."""
    report = await session.get(ReportVersion, report_id)
    if report is None or report.status != "published" or report.published_at is None:
        raise AppError("delivery_not_ready", "A published report is required", 409)
    order = await session.get(Order, report.order_id)
    if order is None:
        raise AppError("not_found", "Order not found", 404)
    if order.price_cents is not None and order.currency is not None:
        paid = await session.scalar(select(PaymentIntent.id).where(
            PaymentIntent.order_id == order.id, PaymentIntent.status == "succeeded",
            PaymentIntent.amount_cents == order.price_cents, PaymentIntent.currency == order.currency))
        if paid is None:
            raise AppError("payment_required", "Order payment has not succeeded", 409)
    return await move(session, order.id, "delivered", "published_report_delivered", "owner", actor_id)
