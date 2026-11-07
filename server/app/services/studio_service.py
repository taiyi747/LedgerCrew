from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.models import AuditLog, Studio, TenantMembership
from app.repositories import records
from app.schemas.studio import StudioCreate
from app.services.access import studio_for_user


async def create_studio(session: AsyncSession, data: StudioCreate, principal: Principal) -> Studio:
    studio = Studio(name=data.name, business_type=data.business_type, owner_user_id=principal.user_id)
    session.add(studio)
    await session.flush()
    if principal.local:
        session.add(TenantMembership(user_id=principal.user_id, studio_id=studio.id))
    session.add(AuditLog(actor_type="customer", actor_id=principal.user_id, action="studio.created", entity_type="studio", entity_id=studio.id))
    await session.commit()
    await session.refresh(studio)
    return studio


async def list_studios(session: AsyncSession, principal: Principal) -> list[Studio]:
    if principal.local and principal.role != "owner":
        memberships = select(TenantMembership.studio_id).where(TenantMembership.user_id == principal.user_id)
        return list((await session.scalars(select(Studio).where(or_(
            Studio.owner_user_id == principal.user_id, Studio.id.in_(memberships)
        )).order_by(Studio.created_at.desc()))).all())
    return await records.list_studios(session, None if principal.role == "owner" else principal.user_id)


async def get_studio(session: AsyncSession, studio_id: str, principal: Principal) -> Studio:
    return await studio_for_user(session, studio_id, principal)
