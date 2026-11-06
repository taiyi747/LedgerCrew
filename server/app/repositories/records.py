from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, Studio, UploadedFile


async def get_studio(session: AsyncSession, studio_id: str) -> Studio | None:
    return await session.get(Studio, studio_id)


async def list_studios(session: AsyncSession, owner_user_id: str) -> list[Studio]:
    return list((await session.scalars(select(Studio).where(Studio.owner_user_id == owner_user_id).order_by(Studio.created_at.desc()))).all())


async def get_order(session: AsyncSession, order_id: str) -> Order | None:
    return await session.get(Order, order_id)


async def list_orders(session: AsyncSession, owner_user_id: str) -> list[Order]:
    return list((await session.scalars(select(Order).join(Studio).where(Studio.owner_user_id == owner_user_id).order_by(Order.created_at.desc()))).all())


async def get_file(session: AsyncSession, file_id: str) -> UploadedFile | None:
    return await session.get(UploadedFile, file_id)


async def list_files(session: AsyncSession, order_id: str) -> list[UploadedFile]:
    return list((await session.scalars(select(UploadedFile).where(UploadedFile.order_id == order_id).order_by(UploadedFile.created_at, UploadedFile.id))).all())
