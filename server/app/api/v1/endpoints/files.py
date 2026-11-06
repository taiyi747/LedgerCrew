from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.file import FileRead
from app.services import file_service
from app.storage.base import Storage
from app.storage.local import get_storage

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{file_id}", response_model=FileRead)
async def get_file(file_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)):
    return await file_service.get_file(session, file_id, principal)


@router.get("/{file_id}/download")
async def download_file(
    file_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal),
    storage: Storage = Depends(get_storage),
):
    record = await file_service.get_file(session, file_id, principal)
    filename = quote(record.original_filename, safe="")
    return Response(
        content=storage.read(record.storage_key), media_type=record.mime_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}", "X-Content-Type-Options": "nosniff"},
    )
