from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.file import ArchiveRead, FileBatchRead, FileRead
from app.schemas.order import OrderCreate, OrderRead
from app.services import file_service, order_service
from app.storage.base import Storage
from app.storage.local import get_storage

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderRead, status_code=201)
async def create_order(data: OrderCreate, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)):
    return await order_service.create_order(session, data, principal)


@router.get("", response_model=list[OrderRead])
async def list_orders(session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)):
    return await order_service.list_orders(session, principal)


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(order_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)):
    return await order_service.get_order(session, order_id, principal)


@router.post("/{order_id}/files", response_model=FileBatchRead, status_code=201)
async def upload_files(
    order_id: str, file_category: str = Form(...), files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal),
    storage: Storage = Depends(get_storage), settings: Settings = Depends(get_settings),
):
    result = await file_service.upload_files(session, storage, order_id, file_category, files, principal, settings)
    return {"files": result}


@router.post("/{order_id}/archives", response_model=ArchiveRead, status_code=201)
async def upload_archive(
    order_id: str, file_category: str = Form(...), file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal),
    storage: Storage = Depends(get_storage), settings: Settings = Depends(get_settings),
):
    archive, entries = await file_service.upload_archive(session, storage, order_id, file_category, file, principal, settings)
    return {"archive": archive, "entries": entries}


@router.get("/{order_id}/files", response_model=list[FileRead])
async def list_files(order_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)):
    return await file_service.list_files(session, order_id, principal)
