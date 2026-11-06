from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CSVImportCreate(BaseModel):
    file_id: str
    column_map: dict[str, str] | None = None


class ImportRowErrorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    reason: str
    raw_row_json: dict[str, Any]


class StatementImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    uploaded_file_id: str
    status: str
    total_rows: int
    success_rows: int
    failed_rows: int
    column_map_json: dict[str, str]
    created_at: datetime
    errors: list[ImportRowErrorRead]


class BankTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    statement_import_id: str
    row_number: int
    external_id: str | None
    transaction_date: date
    counterparty: str
    normalized_counterparty: str
    direction: str
    amount_cents: int
    description: str | None
    raw_row_json: dict[str, Any]
    created_at: datetime
