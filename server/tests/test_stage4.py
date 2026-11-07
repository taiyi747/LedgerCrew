from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import create_order, exercise, png_bytes
from test_stage3 import upload_csv

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import make_engine
from app.schemas.agent import AgentTaskCreate
from app.schemas.reconciliation import InvoiceRecordCreate
from app.services import agent_service
from app.services.reconciliation_engine import InvoiceInput, TransactionInput, reconcile
from app.services.reconciliation_service import persist_invoice

START = date(2026, 10, 1)
END = date(2026, 10, 31)


async def accept_invoice_file(session, order_id: str, file_id: str):
    task = await agent_service.create_task(session, AgentTaskCreate(
        order_id=order_id, agent_role="material_review", task_type="material_review",
        idempotency_key=f"review:{file_id}", correlation_id=f"review:{file_id}",
        input_payload={"order_id": order_id, "file_id": file_id,
                       "file_category": "invoice_image", "mime_type": "image/png"},
    ))
    await agent_service.start_task(session, task.id)
    await agent_service.complete_task(session, task.id, {
        "file_id": file_id, "document_type": "invoice", "review_status": "ACCEPTED",
        "is_invoice": True, "readability": "clear", "reason": None,
        "confidence": 1.0, "next_action": "extract",
    })
    return task


def invoice(id="i1", **changes):
    values = dict(id=id, invoice_number="N-1", issue_date=date(2026, 10, 10),
                  seller="Vendor", buyer="Studio", total_amount_cents=1000,
                  extraction_status="ready", source_sha256=f"hash-{id}")
    values.update(changes)
    return InvoiceInput(**values)


def transaction(id="t1", **changes):
    values = dict(id=id, external_id=f"ref-{id}", transaction_date=date(2026, 10, 12),
                  normalized_counterparty="vendor", direction="OUT", amount_cents=1000,
                  description="service")
    values.update(changes)
    return TransactionInput(**values)


def types(result):
    return [item.exception_type for item in result.tickets]


def test_unique_match_and_bidirectional_identity():
    out = reconcile("ＳＴＵＤＩＯ", START, END, [invoice()], [transaction()])
    assert out.matched_count == 1
    assert out.matches[0].invoice_id == "i1" and out.matches[0].transaction_id == "t1"
    assert out.matches[0].evidence_json["date_difference_days"] == 2
    assert out.exception_count == 0 and out.unmatched_count == 0
    incoming = reconcile("Studio", START, END,
                         [invoice(seller="Studio", buyer="Client")],
                         [transaction(normalized_counterparty="client", direction="IN")])
    assert incoming.matched_count == 1
    boundary = reconcile("Studio", START, END, [invoice()],
                         [transaction(transaction_date=date(2026, 10, 13))])
    assert boundary.matched_count == 1


@pytest.mark.parametrize("change,expected", [
    ({"transaction_date": date(2026, 10, 14)}, "COUNTERPARTY_OR_DATE_CONFLICT"),
    ({"amount_cents": 1001}, "AMOUNT_MISMATCH"),
    ({"direction": "IN"}, "COUNTERPARTY_OR_DATE_CONFLICT"),
    ({"normalized_counterparty": "other"}, "MISSING_TRANSACTION"),
])
def test_nonmatching_conditions(change, expected):
    result = reconcile("Studio", START, END, [invoice()], [transaction(**change)])
    assert result.matches == []
    assert expected in types(result)
    if expected == "AMOUNT_MISMATCH":
        assert result.tickets[0].difference_cents == 1


def test_multiple_candidates_never_force_match_or_reuse_transaction():
    one_invoice = reconcile("Studio", START, END, [invoice()],
                            [transaction("t1"), transaction("t2", external_id="ref-t2")])
    assert one_invoice.matches == []
    assert "MULTIPLE_CANDIDATES" in types(one_invoice)
    two_invoices = reconcile("Studio", START, END,
                             [invoice("i1"), invoice("i2", invoice_number="N-2")],
                             [transaction()])
    assert two_invoices.matches == []
    assert types(two_invoices).count("MULTIPLE_CANDIDATES") == 2


def test_duplicate_invoice_by_number_and_sha_keeps_records():
    result = reconcile("Studio", START, END,
                       [invoice("i1"), invoice("i2", invoice_number="N-1"),
                        invoice("i3", invoice_number=None, source_sha256="same", total_amount_cents=2000),
                        invoice("i4", invoice_number=None, source_sha256="same", total_amount_cents=2000)],
                       [transaction()])
    assert result.matched_count == 1
    assert types(result).count("DUPLICATE_INVOICE") == 2
    assert result.unmatched_count == 3


def test_duplicate_transaction_by_external_id_and_exact_fields():
    result = reconcile("Studio", START, END, [invoice()],
                       [transaction("t1"), transaction("t2", external_id="ref-t1"),
                        transaction("t3", external_id=None), transaction("t4", external_id=None)])
    assert types(result).count("DUPLICATE_TRANSACTION") == 2
    assert result.matches == []  # t1 and t3 remain distinct candidates


def test_missing_invoice_transaction_and_field_conflicts():
    assert types(reconcile("Studio", START, END, [], [transaction()])) == ["MISSING_INVOICE"]
    assert types(reconcile("Studio", START, END, [invoice()], [])) == ["MISSING_TRANSACTION"]
    invalid = reconcile("Studio", START, END, [invoice(issue_date=None)], [])
    assert types(invalid) == ["INVOICE_FIELD_MISSING"]
    assert types(reconcile("Studio", START, END, [invoice(seller="  ")], [])) == ["INVOICE_FIELD_MISSING"]
    assert types(reconcile("Studio", START, END, [invoice(extraction_status="needs_review")], [])) == ["INVOICE_FIELD_MISSING"]
    ambiguous = reconcile("Studio", START, END, [invoice(seller="Studio", buyer="Studio")], [])
    assert types(ambiguous) == ["COUNTERPARTY_OR_DATE_CONFLICT"]


def test_cross_period_never_matches_and_cash_summary_uses_period():
    result = reconcile("Studio", START, END, [invoice(issue_date=date(2026, 11, 1))],
                       [transaction(transaction_date=date(2026, 11, 2))])
    assert result.matches == []
    assert result.income_total_cents == result.expense_total_cents == 0


def test_cash_summary_and_counts_are_integer_cents():
    result = reconcile("Studio", START, END, [invoice()],
                       [transaction(), transaction("income", normalized_counterparty="Client",
                                                   direction="IN", amount_cents=1251),
                        transaction("expense", normalized_counterparty="Other", amount_cents=333)])
    assert result.matched_count == 1
    assert result.unmatched_count == 2
    assert result.exception_count == 2
    assert (result.income_total_cents, result.expense_total_cents, result.net_cash_change_cents) == (1251, 1333, -82)


def test_cash_summary_counts_all_imported_rows_in_period_including_duplicates():
    result = reconcile("Studio", START, END, [],
                       [transaction("t1", direction="IN", amount_cents=501),
                        transaction("t2", external_id="ref-t1", direction="IN", amount_cents=501)])
    assert result.income_total_cents == 1002
    assert "DUPLICATE_TRANSACTION" in types(result)


def test_invoice_input_rejects_float_cents():
    with pytest.raises(ValueError):
        InvoiceRecordCreate(source_file_id="file", total_amount_cents=10.5,
                            extraction_status="ready")


def test_persisted_batch_routes_permission_and_version(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        alice = {"X-User-Id": "alice"}
        bob = {"X-User-Id": "bob"}
        upload = await client.post(
            f"/api/v1/orders/{order_id}/files", data={"file_category": "invoice_image"},
            files=[("files", ("invoice.png", png_bytes(), "image/png"))], headers=alice,
        )
        assert upload.status_code == 201, upload.text
        image_id = upload.json()["files"][0]["id"]
        content = b"transaction_date,counterparty,direction,amount,external_id\n2026-10-12,Vendor,OUT,10.00,bank-1\n"
        csv_id = await upload_csv(client, order_id, content)
        imported = await client.post(f"/api/v1/orders/{order_id}/imports/csv",
                                     json={"file_id": csv_id}, headers=alice)
        assert imported.status_code == 201, imported.text
        engine = make_engine(get_settings().database_url)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                await accept_invoice_file(session, order_id, image_id)
                record = await persist_invoice(session, order_id, InvoiceRecordCreate(
                    source_file_id=image_id, invoice_number="N-1", issue_date=date(2026, 10, 10),
                    seller="Vendor", buyer="Studio", amount_cents=900, tax_cents=100,
                    total_amount_cents=1000, extraction_status="ready",
                    confidence_data={"source": "future_agent"},
                ))
                invoice_id = record.id
                await session.commit()
        finally:
            await engine.dispose()
        assert (await client.get(f"/api/v1/orders/{order_id}/reconciliation", headers=alice)).status_code == 404
        run = await client.post(f"/api/v1/orders/{order_id}/reconciliation/run", headers=alice)
        assert run.status_code == 201, run.text
        batch = run.json()
        assert batch["batch_number"] == 1 and batch["matched_count"] == 1
        assert batch["expense_total_cents"] == 1000 and batch["exception_count"] == 0
        matches = (await client.get(f"/api/v1/orders/{order_id}/matches", headers=alice)).json()
        assert len(matches) == 1 and matches[0]["invoice_id"] == invoice_id
        assert matches[0]["difference_cents"] == 0
        assert (await client.get(f"/api/v1/orders/{order_id}/exceptions", headers=alice)).json() == []
        rerun = await client.post(f"/api/v1/orders/{order_id}/reconciliation/run", headers=alice)
        assert rerun.status_code == 201 and rerun.json()["batch_number"] == 2
        assert rerun.json()["id"] != batch["id"]
        assert (await client.get(f"/api/v1/orders/{order_id}/reconciliation", headers=alice)).json()["id"] == rerun.json()["id"]
        for suffix in ("reconciliation", "matches", "exceptions"):
            assert (await client.get(f"/api/v1/orders/{order_id}/{suffix}", headers=bob)).status_code == 404
        assert (await client.post(f"/api/v1/orders/{order_id}/reconciliation/run", headers=bob)).status_code == 404

    exercise(tmp_path, monkeypatch, scenario)


def test_exception_ticket_persisted_and_invoice_source_validated(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        alice = {"X-User-Id": "alice"}
        csv_id = await upload_csv(
            client, order_id,
            b"transaction_date,counterparty,direction,amount\n2026-10-12,Vendor,OUT,7.25\n",
        )
        imported = await client.post(f"/api/v1/orders/{order_id}/imports/csv",
                                     json={"file_id": csv_id}, headers=alice)
        assert imported.status_code == 201
        engine = make_engine(get_settings().database_url)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                with pytest.raises(AppError) as error:
                    await persist_invoice(session, order_id, InvoiceRecordCreate(
                        source_file_id=csv_id, extraction_status="ready"))
                assert error.value.code == "invalid_invoice_source"
        finally:
            await engine.dispose()
        run = await client.post(f"/api/v1/orders/{order_id}/reconciliation/run", headers=alice)
        assert run.status_code == 201, run.text
        assert run.json()["exception_count"] == 1
        tickets = (await client.get(f"/api/v1/orders/{order_id}/exceptions", headers=alice)).json()
        assert len(tickets) == 1
        assert tickets[0]["exception_type"] == "MISSING_INVOICE"
        assert tickets[0]["status"] == "open"
        assert tickets[0]["related_amount_cents"] == 725
        assert tickets[0]["exception_no"].startswith("EX-")

    exercise(tmp_path, monkeypatch, scenario)
