from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.delivery import ExceptionDecisionCreate, ExceptionDecisionRead, ExceptionSupplementRead
from app.schemas.reconciliation import ExceptionTicketRead
from app.services import exception_service
from app.storage.base import Storage
from app.storage.local import get_storage

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@router.get("/{exception_id}", response_model=ExceptionTicketRead)
async def get_exception(exception_id: str, session: AsyncSession = Depends(get_session),
                        principal: Principal = Depends(get_current_principal)):
    return await exception_service.get_exception(session, exception_id, principal)


@router.post("/{exception_id}/supplements", response_model=ExceptionSupplementRead, status_code=201)
async def add_supplement(
    exception_id: str, explanation: str | None = Form(default=None), file: UploadFile | None = File(default=None),
    existing_file_id: str | None = Form(default=None),
    expected_revision: int | None = Form(default=None),
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal),
    storage: Storage = Depends(get_storage), settings: Settings = Depends(get_settings),
):
    return await exception_service.add_supplement(session, storage, exception_id, principal, settings, explanation, file, existing_file_id, expected_revision)


@router.get("/{exception_id}/supplements", response_model=list[ExceptionSupplementRead])
async def list_supplements(exception_id: str, session: AsyncSession = Depends(get_session),
                           principal: Principal = Depends(get_current_principal)):
    return await exception_service.list_supplements(session, exception_id, principal)


@router.post("/{exception_id}/decisions", response_model=ExceptionDecisionRead, status_code=201)
async def decide(exception_id: str, data: ExceptionDecisionCreate, session: AsyncSession = Depends(get_session),
                 principal: Principal = Depends(get_current_principal)):
    return await exception_service.decide(session, exception_id, data, principal)
