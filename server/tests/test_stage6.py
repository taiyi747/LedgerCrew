import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.db.session import make_engine
from app.models import AgentTask, AuditLog, ExceptionDecision, ReportReviewAction, ReportVersion, UploadedFile
from app.schemas.agent import AgentTaskCreate
from app.schemas.reconciliation import InvoiceRecordCreate
from app.services import agent_service, report_service
from app.services.reconciliation_service import persist_invoice
from test_stage2 import create_order, exercise, png_bytes
from test_stage3 import upload_csv

ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}
OWNER = {"X-User-Id": "owner"}


async def make_batch_with_exception(client, order_id: str):
    content = ("transaction_date,counterparty,direction,amount,description,external_id\n"
               "2026-10-12,Vendor,OUT,10.00,service,tx-1\n"
               "2026-10-13,Unknown,IN,7.25,=1+1,tx-2\n").encode()
    csv_id = await upload_csv(client, order_id, content)
    imported = await client.post(f"/api/v1/orders/{order_id}/imports/csv",
                                 json={"file_id": csv_id}, headers=ALICE)
    assert imported.status_code == 201, imported.text
    upload = await client.post(
        f"/api/v1/orders/{order_id}/files", data={"file_category": "invoice_image"},
        files=[("files", ("invoice.png", png_bytes(), "image/png"))], headers=ALICE,
    )
    assert upload.status_code == 201, upload.text
    file_id = upload.json()["files"][0]["id"]
    engine = make_engine(get_settings().database_url)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            await persist_invoice(session, order_id, InvoiceRecordCreate(
                source_file_id=file_id, invoice_number="INV-1", issue_date=date(2026, 10, 10),
                seller="Vendor", buyer="Studio", amount_cents=900, tax_cents=100,
                total_amount_cents=1000, extraction_status="ready"))
            await session.commit()
    finally:
        await engine.dispose()
    response = await client.post(f"/api/v1/orders/{order_id}/reconciliation/run", headers=ALICE)
    assert response.status_code == 201, response.text
    batch = response.json()
    ticket = (await client.get(f"/api/v1/orders/{order_id}/exceptions", headers=ALICE)).json()[0]
    match = (await client.get(f"/api/v1/orders/{order_id}/matches", headers=ALICE)).json()[0]
    assert ticket["exception_type"] == "MISSING_INVOICE"
    return batch, ticket, match


async def create_report_draft(order_id: str, batch: dict, ticket: dict, match: dict,
                              version: int, content: str) -> ReportVersion:
    engine = make_engine(get_settings().database_url)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            summary = {name: batch[name] for name in ("matched_count", "unmatched_count", "exception_count")}
            summary.update({"batch_id": batch["id"], "match_ids": [match["id"]],
                            "exception_ids": [ticket["id"]]})
            financial = {name: batch[name] for name in (
                "income_total_cents", "expense_total_cents", "net_cash_change_cents")}
            exception_summary = [{
                "exception_id": ticket["id"], "exception_type": ticket["exception_type"],
                "status": ticket["status"], "related_amount_cents": ticket["related_amount_cents"],
                "difference_cents": ticket["difference_cents"],
            }]
            task = await agent_service.create_task(session, AgentTaskCreate(
                order_id=order_id, agent_role="risk_delivery", task_type="report_draft",
                idempotency_key=f"report-v{version}", correlation_id=f"report-corr-{version}",
                input_payload={"order_id": order_id, "report_version": version,
                               "financial_summary": financial,
                               "reconciliation_summary": summary,
                               "exception_summary": exception_summary,
                               "evidence_references": [], "unresolved_items": []},
            ))
            await agent_service.start_task(session, task.id)
            await agent_service.complete_task(session, task.id, {
                "order_id": order_id, "report_version": version, "report_content": content,
                "evidence_references": [], "unresolved_items": [],
            })
            return await report_service.create_from_agent_task(session, task.id)
    finally:
        await engine.dispose()


def test_supplements_and_owner_decisions(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        _, ticket, _ = await make_batch_with_exception(client, order_id)
        url = f"/api/v1/exceptions/{ticket['id']}"
        assert (await client.get(url, headers=BOB)).status_code == 404
        assert (await client.get(url, headers=OWNER)).status_code == 200
        assert (await client.post(f"{url}/decisions", json={
            "decision": "resolve", "reason": "checked", "target_version": 1}, headers=ALICE)).status_code == 403
        requested = await client.post(f"{url}/decisions", json={
            "decision": "request_supplement", "reason": "Need payment note", "target_version": 1}, headers=OWNER)
        assert requested.status_code == 201, requested.text
        assert requested.json()["actor_id"] == "owner"
        assert (await client.get(url, headers=ALICE)).json()["status"] == "waiting_customer"
        text = await client.post(f"{url}/supplements", data={"explanation": "This was a customer refund"}, headers=ALICE)
        assert text.status_code == 201, text.text
        assert text.json()["file_id"] is None
        image = await client.post(f"{url}/supplements", data={"explanation": "Receipt"},
                                  files={"file": ("proof.png", png_bytes(), "image/png")}, headers=ALICE)
        assert image.status_code == 201, image.text
        file_id = image.json()["file_id"]
        assert file_id and (await client.get(f"/api/v1/files/{file_id}", headers=ALICE)).status_code == 200
        assert (await client.get(url, headers=ALICE)).json()["status"] == "waiting_owner"
        supplements = (await client.get(f"{url}/supplements", headers=ALICE)).json()
        assert len(supplements) == 2 and supplements[0]["explanation"] == "This was a customer refund"
        assert (await client.get(f"{url}/supplements", headers=BOB)).status_code == 404
        assert (await client.post(f"{url}/supplements", data={"explanation": ""}, headers=ALICE)).status_code == 422
        assert (await client.post(f"{url}/supplements", files={
            "file": ("notes.txt", b"unsafe evidence", "text/plain")}, headers=ALICE)).status_code == 422
        corrected = await client.post(f"{url}/decisions", json={
            "decision": "correct_classification", "reason": "Refund confirmed",
            "target_version": 1, "classification_after": "customer_refund"}, headers=OWNER)
        assert corrected.status_code == 201 and corrected.json()["classification_before"] is None
        assert (await client.get(url, headers=ALICE)).json()["business_classification"] == "customer_refund"
        reanalyze = await client.post(f"{url}/decisions", json={
            "decision": "reanalyze", "reason": "Review new evidence", "target_version": 1}, headers=OWNER)
        assert reanalyze.status_code == 201
        assert (await client.get(url, headers=ALICE)).json()["status"] == "open"
        accepted = await client.post(f"{url}/decisions", json={
            "decision": "accept_unresolved", "reason": "Deliver with disclosure", "target_version": 1}, headers=OWNER)
        assert accepted.status_code == 201
        assert (await client.get(url, headers=ALICE)).json()["status"] == "accepted_unresolved"
        assert (await client.post(f"{url}/supplements", data={"explanation": "late"}, headers=ALICE)).status_code == 409
        rerun = await client.post(f"/api/v1/orders/{order_id}/reconciliation/run", headers=ALICE)
        assert rerun.status_code == 201
        next_ticket = (await client.get(f"/api/v1/orders/{order_id}/exceptions", headers=ALICE)).json()[0]
        resolved = await client.post(f"/api/v1/exceptions/{next_ticket['id']}/decisions", json={
            "decision": "resolve", "reason": "Verified separately", "target_version": 2}, headers=OWNER)
        assert resolved.status_code == 201
        assert (await client.get(f"/api/v1/exceptions/{next_ticket['id']}", headers=ALICE)).json()["status"] == "resolved"
        engine = make_engine(get_settings().database_url)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                decisions = (await session.scalars(select(ExceptionDecision).where(
                    ExceptionDecision.exception_id == ticket["id"]))).all()
                assert len(decisions) == 4
                assert all(item.target_version == 1 and item.reason for item in decisions)
                queued = (await session.scalars(select(AgentTask).where(
                    AgentTask.idempotency_key == f"reanalyze:{reanalyze.json()['id']}"))).one()
                assert queued.status == "queued" and queued.task_type == "risk_analysis"
                assert queued.input_data["exception_id"] == ticket["id"]
                file = await session.get(UploadedFile, file_id)
                assert file.file_category == "supporting_material" and file.validation_status == "valid"
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_report_approval_versions_permissions_and_exports(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        batch, ticket, match = await make_batch_with_exception(client, order_id)
        report = await create_report_draft(order_id, batch, ticket, match, 1, "October report <script>alert(1)</script>")
        report_url = f"/api/v1/reports/{report.id}"
        assert report.status == "draft" and report.version == 1
        assert batch["income_total_cents"] == 725 and batch["expense_total_cents"] == 1000
        assert report.financial_summary["net_cash_change_cents"] == -275
        assert any(ticket["exception_no"] in item for item in report.unresolved_items)
        assert {ticket["id"], match["id"]} <= set(report.evidence_references)
        assert (await client.get(f"/api/v1/orders/{order_id}/reports", headers=ALICE)).json() == []
        assert (await client.get(report_url, headers=ALICE)).status_code == 404
        assert (await client.get(f"{report_url}/download", headers=ALICE)).status_code == 404
        assert (await client.get(f"/api/v1/orders/{order_id}/exports/invoices.csv", headers=ALICE)).status_code == 404
        assert (await client.get(report_url, headers=OWNER)).status_code == 200
        assert (await client.post(f"{report_url}/approve", headers=OWNER)).status_code == 409
        assert (await client.post(f"{report_url}/submit-review", headers=ALICE)).status_code == 403
        assert (await client.post(f"{report_url}/submit-review", headers=OWNER)).json()["status"] == "in_review"
        assert (await client.post(f"{report_url}/approve", headers=ALICE)).status_code == 403
        assert (await client.post(f"{report_url}/reject", json={"reason": "Revise wording"},
                                  headers=OWNER)).json()["status"] == "draft"
        assert (await client.post(f"{report_url}/submit-review", headers=OWNER)).status_code == 200
        approved = await client.post(f"{report_url}/approve", headers=OWNER)
        assert approved.status_code == 200 and approved.json()["status"] == "approved"
        assert approved.json()["approved_at"] is not None
        assert (await client.get(report_url, headers=ALICE)).status_code == 404
        published = await client.post(f"{report_url}/publish", headers=OWNER)
        assert published.status_code == 200 and published.json()["status"] == "published"
        assert len((await client.get(f"/api/v1/orders/{order_id}/reports", headers=ALICE)).json()) == 1
        assert (await client.get(report_url, headers=BOB)).status_code == 404
        html = await client.get(f"{report_url}/download", headers=ALICE)
        assert html.status_code == 200 and "text/html" in html.headers["content-type"]
        assert ticket["exception_no"] in html.text
        assert "<script>" not in html.text and "&lt;script&gt;" in html.text
        for kind, expected in (("invoices", "INV-1"), ("transactions", "Vendor"),
                               ("matches", match["id"]), ("exceptions", ticket["exception_no"])):
            response = await client.get(f"/api/v1/orders/{order_id}/exports/{kind}.csv", headers=ALICE)
            assert response.status_code == 200, response.text
            assert expected in response.content.decode("utf-8-sig")
            assert (await client.get(f"/api/v1/orders/{order_id}/exports/{kind}.csv", headers=BOB)).status_code == 404
        transactions = await client.get(f"/api/v1/orders/{order_id}/exports/transactions.csv", headers=ALICE)
        rows = list(csv.DictReader(io.StringIO(transactions.content.decode("utf-8-sig"))))
        assert rows[1]["description"] == "'=1+1"
        new_report = await create_report_draft(order_id, batch, ticket, match, 2, "Revised report")
        new_url = f"/api/v1/reports/{new_report.id}"
        assert new_report.content_hash != report.content_hash
        assert (await client.get(new_url, headers=ALICE)).status_code == 404
        assert (await client.post(f"{new_url}/publish", headers=OWNER)).status_code == 409
        assert (await client.post(f"{new_url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{new_url}/approve", headers=OWNER)).status_code == 200
        assert (await client.post(f"{new_url}/publish", headers=OWNER)).status_code == 200
        assert (await client.get(report_url, headers=OWNER)).json()["status"] == "superseded"
        assert (await client.get(report_url, headers=ALICE)).status_code == 200
        assert len((await client.get(f"/api/v1/orders/{order_id}/reports", headers=ALICE)).json()) == 2
        engine = make_engine(get_settings().database_url)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                actions = (await session.scalars(select(ReportReviewAction).where(
                    ReportReviewAction.report_id == report.id))).all()
                assert {item.action for item in actions} == {"approved", "rejected"}
                assert all(item.report_version == 1 and item.content_hash == report.content_hash for item in actions)
                audit = (await session.scalars(select(AuditLog).where(AuditLog.order_id == order_id))).all()
                names = {item.action for item in audit}
                assert {"report.created", "report.modified", "report.approved", "report.published"} <= names
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_report_becomes_stale_after_exception_change(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        batch, ticket, match = await make_batch_with_exception(client, order_id)
        report = await create_report_draft(order_id, batch, ticket, match, 1, "Draft")
        decision = await client.post(f"/api/v1/exceptions/{ticket['id']}/decisions", json={
            "decision": "request_supplement", "reason": "Need proof", "target_version": 1}, headers=OWNER)
        assert decision.status_code == 201
        response = await client.post(f"/api/v1/reports/{report.id}/submit-review", headers=OWNER)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "stale_report"

    exercise(tmp_path, monkeypatch, scenario)


def test_approved_report_content_hash_blocks_unreviewed_changes(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        batch, ticket, match = await make_batch_with_exception(client, order_id)
        report = await create_report_draft(order_id, batch, ticket, match, 1, "Reviewed content")
        url = f"/api/v1/reports/{report.id}"
        assert (await client.post(f"{url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{url}/approve", headers=OWNER)).status_code == 200
        engine = make_engine(get_settings().database_url)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                stored = await session.get(ReportVersion, report.id)
                stored.report_content = "Changed after approval"
                await session.commit()
        finally:
            await engine.dispose()
        response = await client.post(f"{url}/publish", headers=OWNER)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "report_content_changed"
        assert (await client.get(url, headers=ALICE)).status_code == 404

    exercise(tmp_path, monkeypatch, scenario)
