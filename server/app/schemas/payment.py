from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PaymentIntentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    provider: str
    amount_cents: int
    currency: str
    status: str
    refunded_cents: int
    created_at: datetime


class SandboxWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=100)
    intent_id: str = Field(min_length=1, max_length=36)
    event_type: Literal["succeeded", "failed", "cancelled", "refunded"]
    amount_cents: int | None = Field(default=None, gt=0)
