from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.schemas.payment import PaymentIntentRead
from app.services import payment_service

router = APIRouter(tags=["payments"])


@router.post("/orders/{order_id}/payments", response_model=PaymentIntentRead, status_code=201)
async def create_payment(order_id: str, idempotency_key: str = Header(alias="Idempotency-Key"),
                         session: AsyncSession = Depends(get_session),
                         principal: Principal = Depends(get_current_principal)):
    return await payment_service.create_intent(session, order_id, idempotency_key, principal)


@router.get("/orders/{order_id}/payments", response_model=list[PaymentIntentRead])
async def list_payments(order_id: str, session: AsyncSession = Depends(get_session),
                        principal: Principal = Depends(get_current_principal)):
    return await payment_service.list_intents(session, order_id, principal)


@router.post("/payments/sandbox/webhook", response_model=PaymentIntentRead)
async def sandbox_webhook(request: Request,
                          signature: str | None = Header(default=None, alias="X-Sandbox-Signature"),
                          session: AsyncSession = Depends(get_session),
                          settings: Settings = Depends(get_settings)):
    return await payment_service.apply_webhook(session, await request.body(), signature, settings)
