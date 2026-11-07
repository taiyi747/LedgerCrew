"""Sandbox payment state transitions; no real charge or refund is performed."""

import hashlib
import hmac
import secrets
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import Principal
from app.models import AuditLog, PaymentEvent, PaymentIntent, PaymentReconciliation
from app.schemas.payment import SandboxWebhookEvent
from app.services.access import order_for_user


class PaymentProvider(Protocol):
    """A real provider must implement this interface after business approval."""

    name: str

    async def create_intent(self, amount_cents: int, currency: str, idempotency_key: str) -> str: ...


class SandboxPaymentProvider:
    name = "sandbox"

    async def create_intent(self, amount_cents: int, currency: str, idempotency_key: str) -> str:
        return "sb_" + secrets.token_urlsafe(24)


async def create_intent(session: AsyncSession, order_id: str, idempotency_key: str,
                        principal: Principal) -> PaymentIntent:
    order = await order_for_user(session, order_id, principal)
    if not idempotency_key or len(idempotency_key) > 100:
        raise AppError("invalid_idempotency_key", "Idempotency-Key is required", 422)
    if order.price_cents is None or order.price_cents <= 0 or not order.currency:
        raise AppError("pricing_unconfigured", "Order price and currency are not configured", 409)
    existing = await session.scalar(select(PaymentIntent).where(
        PaymentIntent.order_id == order_id, PaymentIntent.idempotency_key == idempotency_key))
    if existing is not None:
        return existing
    active = await session.scalar(select(PaymentIntent).where(
        PaymentIntent.order_id == order_id,
        PaymentIntent.status.in_(("pending", "succeeded", "partially_refunded", "refunded"))))
    if active is not None:
        raise AppError("payment_already_exists", "An active payment already exists for this order", 409)
    provider: PaymentProvider = SandboxPaymentProvider()
    provider_ref = await provider.create_intent(order.price_cents, order.currency, idempotency_key)
    intent = PaymentIntent(order_id=order_id, provider=provider.name, provider_ref=provider_ref,
                           idempotency_key=idempotency_key,
                           amount_cents=order.price_cents, currency=order.currency,
                           status="pending", refunded_cents=0)
    session.add(intent)
    await session.flush()
    session.add(AuditLog(order_id=order_id, actor_type="customer", actor_id=principal.user_id,
                         action="payment.intent_created", entity_type="payment_intent", entity_id=intent.id,
                         details={"provider": "sandbox", "amount_cents": intent.amount_cents,
                                  "currency": intent.currency}))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        previous = await session.scalar(select(PaymentIntent).where(
            PaymentIntent.order_id == order_id, PaymentIntent.idempotency_key == idempotency_key))
        if previous is not None:
            return previous
        raise AppError("payment_already_exists", "An active payment already exists for this order", 409) from exc
    return intent


async def list_intents(session: AsyncSession, order_id: str, principal: Principal) -> list[PaymentIntent]:
    await order_for_user(session, order_id, principal)
    return list((await session.scalars(select(PaymentIntent).where(PaymentIntent.order_id == order_id)
                                       .order_by(PaymentIntent.created_at.desc()))).all())


async def apply_webhook(session: AsyncSession, body: bytes, signature: str | None,
                        settings: Settings) -> PaymentIntent:
    secret = settings.payment_sandbox_webhook_secret
    if secret is None or len(secret.get_secret_value()) < 32:
        raise AppError("payment_unavailable", "Sandbox webhook is not configured", 503)
    expected = hmac.new(secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise AppError("invalid_payment_signature", "Invalid payment signature", 401)
    try:
        event = SandboxWebhookEvent.model_validate_json(body)
    except ValidationError as exc:
        raise AppError("invalid_payment_event", "Invalid payment event", 422) from exc
    previous = await session.scalar(select(PaymentEvent).where(
        PaymentEvent.provider == "sandbox", PaymentEvent.provider_event_id == event.event_id))
    if previous is not None:
        if (previous.intent_id != event.intent_id or previous.event_type != event.event_type
                or previous.amount_cents != event.amount_cents):
            raise AppError("payment_event_conflict", "Payment event ID was reused", 409)
        return await session.get(PaymentIntent, previous.intent_id)
    intent = await session.get(PaymentIntent, event.intent_id)
    if intent is None or intent.provider != "sandbox":
        raise AppError("not_found", "Payment intent not found", 404)
    before = intent.status
    if event.event_type in {"succeeded", "failed", "cancelled"}:
        if before != "pending":
            raise AppError("invalid_payment_transition", "Payment transition is invalid", 409)
        if (event.event_type == "succeeded" and event.amount_cents != intent.amount_cents) or (
            event.event_type != "succeeded" and event.amount_cents is not None
        ):
            raise AppError("payment_amount_mismatch", "Payment amount does not match intent", 409)
        intent.status = event.event_type
    else:
        amount = event.amount_cents
        if before not in {"succeeded", "partially_refunded"} or amount is None:
            raise AppError("invalid_payment_transition", "Refund transition is invalid", 409)
        if intent.refunded_cents + amount > intent.amount_cents:
            raise AppError("refund_exceeds_payment", "Refund exceeds payment amount", 409)
        intent.refunded_cents += amount
        intent.status = "refunded" if intent.refunded_cents == intent.amount_cents else "partially_refunded"
    session.add(PaymentEvent(intent_id=intent.id, provider="sandbox", provider_event_id=event.event_id,
                             event_type=event.event_type, amount_cents=event.amount_cents))
    session.add(PaymentReconciliation(intent_id=intent.id, expected_status=intent.status,
                                      observed_status=intent.status, matched=True))
    session.add(AuditLog(order_id=intent.order_id, actor_type="payment_sandbox", actor_id=event.event_id,
                         action=f"payment.{event.event_type}", entity_type="payment_intent", entity_id=intent.id,
                         details={"from": before, "to": intent.status, "amount_cents": event.amount_cents}))
    await session.commit()
    return intent
