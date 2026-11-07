from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import Principal
from app.models import AuditLog, Order, Studio, TenantMembership
from app.repositories import records
from app.schemas.order import OrderCreate
from app.services.access import order_for_user, studio_for_user


async def create_order(session: AsyncSession, data: OrderCreate, principal: Principal) -> Order:
    await studio_for_user(session, data.studio_id, principal)
    if data.period_end < data.period_start:
        raise AppError("invalid_period", "period_end must be on or after period_start", 422)
    settings = get_settings()
    configured_price = settings.service_prices_cents.get(data.service_scope)
    if configured_price is not None and (configured_price <= 0 or settings.service_currency is None):
        raise AppError("pricing_unconfigured", "Service price and currency must be configured", 503)
    order = Order(
        order_no=f"LC-{uuid4().hex}",
        studio_id=data.studio_id,
        period_start=data.period_start,
        period_end=data.period_end,
        period_year=data.period_start.year,
        period_month=data.period_start.month,
        service_scope=data.service_scope,
        price_cents=configured_price,
        currency=settings.service_currency if configured_price is not None else None,
        is_simulated=True,
        status="draft",
    )
    session.add(order)
    await session.flush()
    session.add(AuditLog(order_id=order.id, actor_type="customer", actor_id=principal.user_id, action="order.created", entity_type="order", entity_id=order.id))
    await session.commit()
    await session.refresh(order)
    return order


async def list_orders(session: AsyncSession, principal: Principal) -> list[Order]:
    if principal.local and principal.role != "owner":
        memberships = select(TenantMembership.studio_id).where(TenantMembership.user_id == principal.user_id)
        return list((await session.scalars(select(Order).join(Studio, Order.studio_id == Studio.id).where(or_(
            Studio.owner_user_id == principal.user_id, Order.studio_id.in_(memberships)
        )).order_by(Order.created_at.desc()))).all())
    return await records.list_orders(session, None if principal.role == "owner" else principal.user_id)


async def get_order(session: AsyncSession, order_id: str, principal: Principal) -> Order:
    return await order_for_user(session, order_id, principal)
