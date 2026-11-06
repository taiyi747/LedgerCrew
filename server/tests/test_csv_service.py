import json

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.services.csv_service import CSVService

MAP = {
    "transaction_date": "transaction_date",
    "counterparty": "counterparty",
    "direction": "direction",
    "amount": "amount",
    "description": "description",
    "external_id": "external_id",
}
HEADER = "transaction_date,counterparty,direction,amount,description,external_id\n"


def test_valid_csv_bom_decimal_and_raw_row() -> None:
    content = (HEADER + "2026-10-01,ＡＣＭＥ   Co,IN,12.34,service,txn-1\n").encode("utf-8-sig")
    result = CSVService(MAP).parse(content)
    assert result.total_rows == 1
    assert not result.errors
    row = result.transactions[0]
    assert row.row_number == 2
    assert row.amount_cents == 1234
    assert row.normalized_counterparty == "acme co"
    assert row.raw_row_json["counterparty"] == "ＡＣＭＥ   Co"


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("2026-13-01,A,IN,1.00,,x", "invalid_date"),
        ("2026-1-1,A,IN,1.00,,x", "invalid_date"),
        ("2026-10-01,A,IN,abc,,x", "invalid_amount"),
        ("2026-10-01,A,IN,1.234,,x", "amount_precision"),
        ("2026-10-01,A,IN,0,,x", "invalid_amount"),
        ("2026-10-01,A,IN,92233720368547758.08,,x", "amount_out_of_range"),
        ("2026-10-01,A,in,1.00,,x", "invalid_direction"),
    ],
)
def test_row_validation(row: str, reason: str) -> None:
    result = CSVService(MAP).parse((HEADER + row + "\n").encode())
    assert result.total_rows == 1
    assert not result.transactions
    assert result.errors[0].reason == reason
    assert result.errors[0].row_number == 2


def test_duplicate_external_id_is_row_error_and_other_rows_survive() -> None:
    content = (HEADER + "2026-10-01,A,IN,1.00,,same\n2026-10-02,B,OUT,2.00,,same\n2026-10-03,C,IN,3.00,,other\n").encode()
    result = CSVService(MAP).parse(content)
    assert result.total_rows == 3
    assert [row.external_id for row in result.transactions] == ["same", "other"]
    assert [(error.row_number, error.reason) for error in result.errors] == [(3, "duplicate_external_id")]


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", "empty_csv"),
        (HEADER.encode(), "empty_csv"),
        (b"\xff\xfe", "invalid_csv_encoding"),
        (b"transaction_date,counterparty,amount\n2026-10-01,A,1.00\n", "missing_csv_columns"),
    ],
)
def test_file_level_errors(content: bytes, code: str) -> None:
    with pytest.raises(AppError) as error:
        CSVService(MAP).parse(content)
    assert error.value.code == code


def test_configurable_header_mapping() -> None:
    mapping = {"transaction_date": "Date", "counterparty": "Payee", "direction": "Flow", "amount": "Value"}
    result = CSVService(mapping).parse(b"Date,Payee,Flow,Value\n2026-10-01,Vendor,OUT,9.99\n")
    assert result.transactions[0].amount_cents == 999
    assert result.transactions[0].description is None


def test_column_mapping_loads_from_environment(monkeypatch) -> None:
    mapping = {"transaction_date": "Date", "counterparty": "Payee", "direction": "Flow", "amount": "Value"}
    monkeypatch.setenv("CSV_COLUMN_MAP", json.dumps(mapping))
    assert Settings().csv_column_map == mapping
