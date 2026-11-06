from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.transaction import StatementImportRead
from app.services import import_service

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("/{import_id}", response_model=StatementImportRead)
async def get_import(
    import_id: str, session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    return await import_service.get_import(session, import_id, principal)
