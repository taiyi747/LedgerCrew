"""Exact decimal text to SQLite-safe integer cents."""

import re
from decimal import Decimal

from app.core.exceptions import AppError

MAX_CENTS = 2**63 - 1


def parse_cents(value: str | None, *, allow_zero: bool = False) -> int | None:
    if value is None:
        return None
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value):
        raise AppError("invalid_invoice_amount", "Invoice amount must have at most two decimal places", 422)
    cents = int(Decimal(value) * 100)
    if cents > MAX_CENTS or (cents == 0 and not allow_zero):
        raise AppError("invalid_invoice_amount", "Invoice amount is out of range", 422)
    return cents
