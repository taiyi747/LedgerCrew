from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.studio import StudioCreate, StudioRead
from app.services import studio_service

router = APIRouter(prefix="/studios", tags=["studios"])


@router.post("", response_model=StudioRead, status_code=201)
async def create_studio(data: StudioCreate, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)):
    return await studio_service.create_studio(session, data, principal)


@router.get("", response_model=list[StudioRead])
async def list_studios(session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)):
    return await studio_service.list_studios(session, principal)


@router.get("/{studio_id}", response_model=StudioRead)
async def get_studio(studio_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)):
    return await studio_service.get_studio(session, studio_id, principal)
