from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.reconciliation import ExceptionTicketRead, ReconciliationBatchRead, ReconciliationMatchRead
from app.services import reconciliation_service

router = APIRouter(prefix="/orders/{order_id}", tags=["reconciliation"])


@router.post("/reconciliation/run", response_model=ReconciliationBatchRead, status_code=201)
async def run_reconciliation(order_id: str, session: AsyncSession = Depends(get_session),
                             principal: Principal = Depends(get_current_principal)):
    return await reconciliation_service.run(session, order_id, principal)


@router.get("/reconciliation", response_model=ReconciliationBatchRead)
async def get_reconciliation(order_id: str, session: AsyncSession = Depends(get_session),
                             principal: Principal = Depends(get_current_principal)):
    return await reconciliation_service.get_latest(session, order_id, principal)


@router.get("/matches", response_model=list[ReconciliationMatchRead])
async def get_matches(order_id: str, session: AsyncSession = Depends(get_session),
                      principal: Principal = Depends(get_current_principal)):
    return await reconciliation_service.get_matches(session, order_id, principal)


@router.get("/exceptions", response_model=list[ExceptionTicketRead])
async def get_exceptions(order_id: str, session: AsyncSession = Depends(get_session),
                         principal: Principal = Depends(get_current_principal)):
    return await reconciliation_service.get_exceptions(session, order_id, principal)
