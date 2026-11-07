"""Synthetic regression checks for the existing order-scoped CSV importer.

These tests do not assert a v0.2 platform deduplication policy.
"""

import hashlib
import sqlite3

from test_stage2 import create_order, exercise

from app.core.config import get_settings

HEADERS = {"X-User-Id": "alice"}
CSV_HEADER = "transaction_date,counterparty,direction,amount,description,external_id\n"


async def upload_csv(client, order_id: str, filename: str, content: bytes) -> dict:
    response = await client.post(
        f"/api/v1/orders/{order_id}/files",
        data={"file_category": "bank_statement_csv"},
        files=[("files", (filename, content, "text/csv"))],
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()["files"][0]


async def import_file(client, order_id: str, file_id: str):
    return await client.post(
        f"/api/v1/orders/{order_id}/imports/csv",
        json={"file_id": file_id},
        headers=HEADERS,
    )


def count_rows(table: str, *, where: str = "1=1") -> int:
    # Only fixed table names and predicates from this test module are passed here.
    db_path = get_settings().database_url.removeprefix("sqlite+aiosqlite:///")
    with sqlite3.connect(db_path) as connection:
        return connection.execute(f"SELECT count(*) FROM {table} WHERE {where}").fetchone()[0]


def test_within_file_external_id_duplicate_keeps_evidence_and_retry_is_idempotent(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        content = (CSV_HEADER
                   + "2026-10-01,Client A,IN,12.34,first,ref-1\n"
                   + "2026-10-02,Client B,IN,99.00,conflict,ref-1\n").encode()
        file = await upload_csv(client, order_id, "first.csv", content)
        assert file["sha256"] == hashlib.sha256(content).hexdigest()
        first = await import_file(client, order_id, file["id"])
        assert first.status_code == 201, first.text
        imported = first.json()
        assert (imported["total_rows"], imported["success_rows"], imported["failed_rows"]) == (2, 1, 1)
        assert imported["errors"][0]["reason"] == "duplicate_external_id"
        assert imported["errors"][0]["raw_row_json"]["counterparty"] == "Client B"
        assert imported["uploaded_file_id"] == file["id"]

        repeated = await import_file(client, order_id, file["id"])
        assert repeated.status_code == 201
        assert repeated.json()["id"] == imported["id"]
        transactions = (await client.get(f"/api/v1/orders/{order_id}/transactions", headers=HEADERS)).json()
        assert len(transactions) == 1
        assert transactions[0]["statement_import_id"] == imported["id"]
        assert transactions[0]["row_number"] == 2
        assert transactions[0]["external_id"] == "ref-1"
        assert transactions[0]["amount_cents"] == 1234
        assert transactions[0]["raw_row_json"]["amount"] == "12.34"
        assert (await client.get(f"/api/v1/files/{file['id']}/download", headers=HEADERS)).content == content
        assert count_rows("statement_imports") == 1
        assert count_rows("statement_import_errors") == 1
        assert count_rows("audit_logs", where="action='statement.imported'") == 1

    exercise(tmp_path, monkeypatch, scenario)


def test_reuploaded_identical_bytes_are_separate_mvp_imports(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        content = (CSV_HEADER + "2026-10-01,Client A,IN,12.34,first,ref-1\n").encode()
        first_file = await upload_csv(client, order_id, "export-a.csv", content)
        same_name_file = await upload_csv(client, order_id, "export-a.csv", content)
        second_file = await upload_csv(client, order_id, "export-b.csv", content)
        assert len({item["id"] for item in (first_file, same_name_file, second_file)}) == 3
        assert len({item["sha256"] for item in (first_file, same_name_file, second_file)}) == 1
        imports = [await import_file(client, order_id, item["id"])
                   for item in (first_file, same_name_file, second_file)]
        assert all(item.status_code == 201 for item in imports)
        assert len({item.json()["id"] for item in imports}) == 3
        transactions = (await client.get(f"/api/v1/orders/{order_id}/transactions", headers=HEADERS)).json()
        assert len(transactions) == 3
        assert {row["statement_import_id"] for row in transactions} == {item.json()["id"] for item in imports}
        assert {row["external_id"] for row in transactions} == {"ref-1"}
        assert count_rows("statement_imports") == 3

    exercise(tmp_path, monkeypatch, scenario)


def test_rows_without_external_id_remain_distinct_and_traceable(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        content = (CSV_HEADER
                   + "2026-10-01,Client A,IN,12.34,same,\n"
                   + "2026-10-01,Client A,IN,12.34,same,\n"
                   + "2026-10-02,Client A,IN,12.34,other date,\n"
                   + "2026-10-01,Client B,IN,12.34,other party,\n").encode()
        file = await upload_csv(client, order_id, "no-ids.csv", content)
        imported = await import_file(client, order_id, file["id"])
        assert imported.status_code == 201, imported.text
        assert (imported.json()["success_rows"], imported.json()["failed_rows"]) == (4, 0)
        transactions = (await client.get(f"/api/v1/orders/{order_id}/transactions", headers=HEADERS)).json()
        assert len(transactions) == 4
        assert {row["row_number"] for row in transactions} == {2, 3, 4, 5}
        assert all(row["external_id"] is None and row["statement_import_id"] == imported.json()["id"]
                   for row in transactions)
        assert sum(row["raw_row_json"]["description"] == "same" for row in transactions) == 2
        assert {row["transaction_date"] for row in transactions} == {"2026-10-01", "2026-10-02"}
        assert {row["counterparty"] for row in transactions} == {"Client A", "Client B"}

    exercise(tmp_path, monkeypatch, scenario)


def test_failed_parse_retry_has_no_partial_database_side_effects(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        content = (CSV_HEADER
                   + "2026-10-01,Client A,IN,12.34,first,ref-1\n"
                   + "2026-10-02,Client B,IN,20.00,second,ref-2\n").encode()
        file = await upload_csv(client, order_id, "too-many.csv", content)
        for _ in range(2):
            result = await import_file(client, order_id, file["id"])
            assert result.status_code == 413
            assert result.json()["error"]["code"] == "csv_row_limit"
        assert (await client.get(f"/api/v1/orders/{order_id}/imports", headers=HEADERS)).json() == []
        assert (await client.get(f"/api/v1/orders/{order_id}/transactions", headers=HEADERS)).json() == []
        assert (await client.get(f"/api/v1/files/{file['id']}/download", headers=HEADERS)).content == content
        assert count_rows("statement_imports") == 0
        assert count_rows("bank_transactions") == 0
        assert count_rows("audit_logs", where="action='statement.imported'") == 0

    exercise(tmp_path, monkeypatch, scenario, csv_max_rows=1)
