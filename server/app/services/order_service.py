from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import Principal
from app.models import AuditLog, Order
from app.repositories import records
from app.schemas.order import OrderCreate
from app.services.access import order_for_user, studio_for_user


async def create_order(session: AsyncSession, data: OrderCreate, principal: Principal, *, commit: bool = True) -> Order:
    await studio_for_user(session, data.studio_id, principal)
    if data.period_end < data.period_start:
        raise AppError("invalid_period", "period_end must be on or after period_start", 422)
    order = Order(
        order_no=f"LC-{uuid4().hex}",
        studio_id=data.studio_id,
        period_start=data.period_start,
        period_end=data.period_end,
        period_year=data.period_start.year,
        period_month=data.period_start.month,
        service_scope=data.service_scope,
        is_simulated=True,
        status="draft",
    )
    session.add(order)
    await session.flush()
    session.add(AuditLog(order_id=order.id, actor_type="customer", actor_id=principal.user_id, action="order.created", entity_type="order", entity_id=order.id))
    if commit:
        await session.commit()
    else:
        await session.flush()
    await session.refresh(order)
    return order


async def list_orders(session: AsyncSession, principal: Principal) -> list[Order]:
    return await records.list_orders(session, None if principal.role == "owner" else principal.user_id)


async def get_order(session: AsyncSession, order_id: str, principal: Principal) -> Order:
    return await order_for_user(session, order_id, principal)
