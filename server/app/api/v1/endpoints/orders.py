from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.file import ArchiveRead, FileBatchRead, FileRead
from app.schemas.order import OrderCreate, OrderRead
from app.schemas.transaction import BankTransactionRead, CSVImportCreate, StatementImportRead
from app.services import file_service, import_service, order_service
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
    replaces_file_id: str | None = Form(default=None),
    expected_revision: int | None = Form(default=None),
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal),
    storage: Storage = Depends(get_storage), settings: Settings = Depends(get_settings),
):
    result = await file_service.upload_files(session, storage, order_id, file_category, files, principal, settings, replaces_file_id, expected_revision)
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


@router.post("/{order_id}/imports/csv", response_model=StatementImportRead, status_code=201)
async def import_csv(
    order_id: str, data: CSVImportCreate, session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal), storage: Storage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    return await import_service.import_csv(session, storage, order_id, data, principal, settings)


@router.get("/{order_id}/imports", response_model=list[StatementImportRead])
async def list_imports(
    order_id: str, session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    return await import_service.list_imports(session, order_id, principal)


@router.get("/{order_id}/transactions", response_model=list[BankTransactionRead])
async def list_transactions(
    order_id: str, session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    return await import_service.list_transactions(session, order_id, principal)
