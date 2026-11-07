import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.exceptions import AppError

REQUIRED_COLUMNS = {"transaction_date", "counterparty", "direction", "amount"}
OPTIONAL_COLUMNS = {"description", "external_id"}
ALL_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS
MAX_AMOUNT = Decimal("92233720368547758.07")


@dataclass(frozen=True)
class ParsedTransaction:
    row_number: int
    external_id: str | None
    transaction_date: date
    counterparty: str
    normalized_counterparty: str
    direction: str
    amount_cents: int
    description: str | None
    raw_row_json: dict[str, Any]


@dataclass(frozen=True)
class ParsedRowError:
    row_number: int
    reason: str
    raw_row_json: dict[str, Any]


@dataclass(frozen=True)
class ParsedCSV:
    total_rows: int
    transactions: list[ParsedTransaction]
    errors: list[ParsedRowError]


def normalize_counterparty(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


class CSVService:
    def __init__(self, column_map: dict[str, str], date_format: str = "%Y-%m-%d", max_rows: int = 200) -> None:
        if not column_map.keys() >= REQUIRED_COLUMNS or not column_map.keys() <= ALL_COLUMNS:
            raise AppError("invalid_column_map", "Column map must define required standard fields only", 422)
        if any(not name.strip() for name in column_map.values()) or len(set(column_map.values())) != len(column_map):
            raise AppError("invalid_column_map", "Column names must be nonempty and unique", 422)
        self.column_map = column_map
        self.date_format = date_format
        self.max_rows = max_rows

    def parse(self, content: bytes) -> ParsedCSV:
        if not content:
            raise AppError("empty_csv", "CSV file is empty", 422)
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AppError("invalid_csv_encoding", "CSV must be UTF-8 or UTF-8 BOM", 422) from exc
        if "\x00" in decoded or not decoded.strip():
            raise AppError("empty_csv", "CSV file is empty or contains binary data", 422)
        reader = csv.reader(io.StringIO(decoded, newline=""), strict=True)
        try:
            header = [name.strip() for name in next(reader)]
        except StopIteration as exc:
            raise AppError("empty_csv", "CSV file is empty", 422) from exc
        except csv.Error as exc:
            raise AppError("invalid_csv", "CSV header cannot be parsed", 422) from exc
        if not header or any(not name for name in header) or len(set(header)) != len(header):
            raise AppError("invalid_csv_header", "CSV header is empty or has duplicate columns", 422)
        missing = sorted(self.column_map[field] for field in REQUIRED_COLUMNS if self.column_map[field] not in header)
        if missing:
            raise AppError("missing_csv_columns", f"Missing required CSV columns: {', '.join(missing)}", 422)

        transactions: list[ParsedTransaction] = []
        errors: list[ParsedRowError] = []
        seen_external_ids: set[str] = set()
        total_rows = 0
        try:
            for values in reader:
                if not values:
                    continue
                total_rows += 1
                if total_rows > self.max_rows:
                    raise AppError("csv_row_limit", "CSV exceeds configured row limit", 413)
                row_number = reader.line_num
                raw: dict[str, Any] = dict(zip(header, values, strict=False))
                if len(values) > len(header):
                    raw["__extra__"] = values[len(header):]
                    errors.append(ParsedRowError(row_number, "column_count_mismatch", raw))
                    continue
                parsed, reason = self._parse_row(row_number, raw)
                if reason:
                    errors.append(ParsedRowError(row_number, reason, raw))
                elif parsed.external_id and parsed.external_id in seen_external_ids:
                    errors.append(ParsedRowError(row_number, "duplicate_external_id", raw))
                else:
                    transactions.append(parsed)
                    if parsed.external_id:
                        seen_external_ids.add(parsed.external_id)
        except csv.Error as exc:
            raise AppError("invalid_csv", "CSV data cannot be parsed", 422) from exc
        if total_rows == 0:
            raise AppError("empty_csv", "CSV contains no data rows", 422)
        return ParsedCSV(total_rows, transactions, errors)

    def _parse_row(self, row_number: int, raw: dict[str, Any]) -> tuple[ParsedTransaction | None, str | None]:
        values = {field: str(raw.get(column, "")).strip() for field, column in self.column_map.items()}
        if any(not values[field] for field in REQUIRED_COLUMNS):
            return None, "missing_required_value"
        try:
            transaction_date = datetime.strptime(values["transaction_date"], self.date_format).date()
            if transaction_date.strftime(self.date_format) != values["transaction_date"]:
                raise ValueError("Date format mismatch")
        except ValueError:
            return None, "invalid_date"
        counterparty = values["counterparty"]
        normalized = normalize_counterparty(counterparty)
        if len(counterparty) > 300 or len(normalized) > 300:
            return None, "counterparty_too_long"
        direction = values["direction"]
        if direction not in {"IN", "OUT"}:
            return None, "invalid_direction"
        amount_text = values["amount"]
        try:
            amount = Decimal(amount_text)
        except InvalidOperation:
            return None, "invalid_amount"
        if not amount.is_finite() or amount <= 0:
            return None, "invalid_amount"
        if amount.as_tuple().exponent < -2:
            return None, "amount_precision"
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", amount_text):
            return None, "invalid_amount"
        if amount > MAX_AMOUNT:
            return None, "amount_out_of_range"
        external_id = values.get("external_id") or None
        if external_id and len(external_id) > 200:
            return None, "external_id_too_long"
        return ParsedTransaction(
            row_number=row_number,
            external_id=external_id,
            transaction_date=transaction_date,
            counterparty=counterparty,
            normalized_counterparty=normalized,
            direction=direction,
            amount_cents=int(amount * Decimal(100)),
            description=values.get("description") or None,
            raw_row_json=raw,
        ), None
