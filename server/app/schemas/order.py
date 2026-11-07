from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    studio_id: str
    period_start: date
    period_end: date
    service_scope: str = Field(min_length=1, max_length=200)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_no: str
    studio_id: str
    period_start: date
    period_end: date
    status: str
    input_revision: int
    service_scope: str | None
    price_cents: int | None
    intake_id: str | None
    service_snapshot: dict | None
    is_simulated: bool
    created_at: datetime
    updated_at: datetime
