from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class InvoiceRecordCreate(BaseModel):
    """Validated data boundary for a future invoice-processing integration."""

    source_file_id: str
    invoice_number: str | None = Field(default=None, max_length=100)
    issue_date: date | None = None
    seller: str | None = Field(default=None, max_length=300)
    buyer: str | None = Field(default=None, max_length=300)
    amount_cents: StrictInt | None = Field(default=None, ge=0)
    tax_cents: StrictInt | None = Field(default=None, ge=0)
    total_amount_cents: StrictInt | None = Field(default=None, gt=0)
    extraction_status: Literal["ready", "needs_review", "invalid"]
    confidence_data: dict[str, Any] | None = None


class InvoiceRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    source_file_id: str
    invoice_number: str | None
    issue_date: date | None
    seller: str | None
    buyer: str | None
    amount_cents: int | None
    tax_cents: int | None
    total_amount_cents: int | None
    extraction_status: str
    confidence_data: dict[str, Any] | None
    created_at: datetime


class ReconciliationBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    batch_number: int
    income_total_cents: int
    expense_total_cents: int
    net_cash_change_cents: int
    matched_count: int
    unmatched_count: int
    exception_count: int
    created_at: datetime


class ReconciliationMatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    batch_id: str
    invoice_id: str
    transaction_id: str
    match_status: str
    difference_cents: int
    match_rule: str
    evidence_json: dict[str, Any]
    created_at: datetime


class ExceptionTicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exception_no: str
    batch_id: str
    order_id: str
    exception_type: str
    invoice_id: str | None
    transaction_id: str | None
    related_amount_cents: int | None
    difference_cents: int | None
    status: str
    evidence_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
