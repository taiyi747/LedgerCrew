from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import Principal
from app.models import Order, Studio, TenantMembership, UploadedFile
from app.repositories import records


async def studio_for_user(session: AsyncSession, studio_id: str, principal: Principal) -> Studio:
    studio = await records.get_studio(session, studio_id)
    if studio is None:
        raise AppError("not_found", "Studio not found", 404)
    if principal.role != "owner" and studio.owner_user_id != principal.user_id:
        membership = (await session.scalar(select(TenantMembership.id).where(
            TenantMembership.studio_id == studio_id, TenantMembership.user_id == principal.user_id))
            if principal.local else None)
        if membership is None:
            raise AppError("not_found", "Studio not found", 404)
    return studio


async def order_for_user(session: AsyncSession, order_id: str, principal: Principal) -> Order:
    order = await records.get_order(session, order_id)
    if order is None:
        raise AppError("not_found", "Order not found", 404)
    await studio_for_user(session, order.studio_id, principal)
    return order


async def file_for_user(session: AsyncSession, file_id: str, principal: Principal) -> UploadedFile:
    file = await records.get_file(session, file_id)
    if file is None:
        raise AppError("not_found", "File not found", 404)
    await order_for_user(session, file.order_id, principal)
    return file
