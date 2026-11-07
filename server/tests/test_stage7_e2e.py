import hashlib

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import create_order, exercise, png_bytes, zip_bytes
from test_stage3 import upload_csv

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import make_engine
from app.integrations.agents.fake_gateway import FakeAgentGateway, FakeResult
from app.models import BankTransaction, InvoiceRecord, UploadedFile
from app.schemas.agent import AgentTaskCreate
from app.schemas.reconciliation import InvoiceRecordCreate
from app.services import agent_service, report_service
from app.services.reconciliation_service import persist_invoice, persist_invoice_from_task
from app.storage.local import LocalStorage

ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}
OWNER = {"X-User-Id": "owner"}


async def order_status(client, order_id: str) -> str:
    response = await client.get(f"/api/v1/orders/{order_id}", headers=ALICE)
    assert response.status_code == 200, response.text
    return response.json()["status"]


def test_full_monthly_flow_with_fake_agents(tmp_path, monkeypatch):
    async def scenario(client, storage_root):
        studio_id, order_id = await create_order(client)
        assert (await client.get(f"/api/v1/studios/{studio_id}", headers=BOB)).status_code == 404
        assert await order_status(client, order_id) == "draft"
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        original_image = png_bytes()
        try:
            async with sessions() as session:
                reception = await agent_service.create_task(session, AgentTaskCreate(
                    order_id=order_id, agent_role="customer_reception", task_type="customer_reception",
                    idempotency_key="reception-v1", correlation_id="flow-1",
                    input_payload={"order_id": order_id, "customer_message": "整理十月账目",
                                   "submitted_file_ids": []},
                ))
                gateway = FakeAgentGateway({"customer_reception": FakeResult("succeeded", {
                    "needs_summary": "October records", "material_reminders": ["invoice", "statement"],
                    "follow_up_questions": [],
                })})
                assert (await agent_service.invoke_task(session, reception.id, gateway)).status == "succeeded"
                assert (await agent_service.invoke_task(session, reception.id, gateway)).id == reception.id
                assert len(gateway.requests) == 1
            uploaded = await client.post(f"/api/v1/orders/{order_id}/files",
                                         data={"file_category": "invoice_image"},
                                         files=[("files", ("invoice.png", original_image, "image/png"))],
                                         headers=ALICE)
            assert uploaded.status_code == 201, uploaded.text
            file_id = uploaded.json()["files"][0]["id"]
            assert uploaded.json()["files"][0]["sha256"] == hashlib.sha256(original_image).hexdigest()
            assert "storage_key" not in uploaded.text
            assert await order_status(client, order_id) == "awaiting_materials"
            csv_bytes = ("transaction_date,counterparty,direction,amount,description,external_id\n"
                         "2026-10-12,Vendor,OUT,10.00,design,bank-1\n"
                         "2026-10-13,Other,IN,7.25,deposit,bank-2\n").encode("utf-8-sig")
            csv_id = await upload_csv(client, order_id, csv_bytes)
            assert await order_status(client, order_id) == "ready_to_process"
            archive_content = zip_bytes({"batch/rejected.png": original_image})
            archive = await client.post(f"/api/v1/orders/{order_id}/archives",
                                        data={"file_category": "invoice_image"},
                                        files={"file": ("batch.zip", archive_content, "application/zip")},
                                        headers=ALICE)
            assert archive.status_code == 201, archive.text
            archive_id = archive.json()["archive"]["id"]
            entry = archive.json()["entries"][0]
            assert entry["archive_file_id"] == archive_id
            assert entry["archive_entry_path"] == "batch/rejected.png"
            assert entry["upload_source"] == "archive" and entry["validation_status"] == "valid"
            assert (await client.get(f"/api/v1/files/{archive_id}/download", headers=ALICE)).content == archive_content
            assert await order_status(client, order_id) == "ready_to_process"
            imported = await client.post(f"/api/v1/orders/{order_id}/imports/csv",
                                         json={"file_id": csv_id}, headers=ALICE)
            assert imported.status_code == 201 and imported.json()["success_rows"] == 2
            transactions = (await client.get(f"/api/v1/orders/{order_id}/transactions", headers=ALICE)).json()
            assert transactions[0]["raw_row_json"]["amount"] == "10.00"
            assert transactions[0]["amount_cents"] == 1000
            original_rows = [item["raw_row_json"] for item in transactions]
            async with sessions() as session:
                rejected_review = await agent_service.create_task(session, AgentTaskCreate(
                    order_id=order_id, agent_role="material_review", task_type="material_review",
                    idempotency_key="review-zip", correlation_id="flow-1",
                    input_payload={"order_id": order_id, "file_id": entry["id"],
                                   "file_category": "invoice_image", "mime_type": "image/png"},
                ))
                rejected_fake = FakeAgentGateway({"material_review": FakeResult("succeeded", {
                    "file_id": entry["id"], "document_type": "invoice", "review_status": "REJECTED",
                    "is_invoice": True, "readability": "poor", "reason": "unreadable",
                    "confidence": 0.9, "next_action": "reupload",
                })})
                assert (await agent_service.invoke_task(session, rejected_review.id, rejected_fake)).status == "succeeded"
                try:
                    await agent_service.create_task(session, AgentTaskCreate(
                        order_id=order_id, agent_role="invoice_processing", task_type="invoice_extraction",
                        idempotency_key="extract-rejected", correlation_id="flow-1",
                        input_payload={"order_id": order_id, "file_id": entry["id"], "mime_type": "image/png"},
                    ))
                    raise AssertionError("Rejected invoice must not enter extraction")
                except AppError as exc:
                    assert exc.code == "invoice_review_required"
                accepted_review = await agent_service.create_task(session, AgentTaskCreate(
                    order_id=order_id, agent_role="material_review", task_type="material_review",
                    idempotency_key="review-direct", correlation_id="flow-1",
                    input_payload={"order_id": order_id, "file_id": file_id,
                                   "file_category": "invoice_image", "mime_type": "image/png"},
                ))
                accepted_fake = FakeAgentGateway({"material_review": FakeResult("succeeded", {
                    "file_id": file_id, "document_type": "invoice", "review_status": "ACCEPTED",
                    "is_invoice": True, "readability": "clear", "reason": None,
                    "confidence": 0.99, "next_action": "extract",
                })})
                assert (await agent_service.invoke_task(session, accepted_review.id, accepted_fake)).status == "succeeded"
                extraction_data = AgentTaskCreate(
                    order_id=order_id, agent_role="invoice_processing", task_type="invoice_extraction",
                    idempotency_key="extract-direct", correlation_id="flow-1",
                    input_payload={"order_id": order_id, "file_id": file_id, "mime_type": "image/png"},
                )
                extraction = await agent_service.create_task(session, extraction_data)
                assert (await agent_service.create_task(session, extraction_data)).id == extraction.id
                extraction_fake = FakeAgentGateway({"invoice_extraction": FakeResult("succeeded", {
                    "file_id": file_id, "invoice_number": "INV-10", "issue_date": "2026-10-10",
                    "seller": "Vendor", "buyer": "Studio", "amount": "9.00",
                    "tax_amount": "1.00", "total_amount": "10.00", "invoice_type": "standard",
                    "confidence": 0.98, "missing_fields": [], "extraction_status": "ready",
                })})
                assert (await agent_service.invoke_task(session, extraction.id, extraction_fake)).status == "succeeded"
                invoice = await persist_invoice_from_task(session, extraction.id)
                assert invoice.amount_cents == 900 and invoice.tax_cents == 100
                assert invoice.total_amount_cents == 1000
                assert invoice.source_file_id == file_id and invoice.source_task_id == extraction.id
                assert invoice.material_review_task_id == accepted_review.id
                await session.commit()
                assert (await persist_invoice_from_task(session, extraction.id)).id == invoice.id
            assert await order_status(client, order_id) == "processing"
            assert (await client.get(f"/api/v1/files/{file_id}/download", headers=ALICE)).content == original_image
            assert (await client.get(f"/api/v1/files/{file_id}", headers=BOB)).status_code == 404
            run = await client.post(f"/api/v1/orders/{order_id}/reconciliation/run", headers=ALICE)
            assert run.status_code == 201, run.text
            batch = run.json()
            assert (batch["income_total_cents"], batch["expense_total_cents"],
                    batch["net_cash_change_cents"]) == (725, 1000, -275)
            assert batch["matched_count"] == 1 and batch["exception_count"] == 1
            match = (await client.get(f"/api/v1/orders/{order_id}/matches", headers=ALICE)).json()[0]
            ticket = (await client.get(f"/api/v1/orders/{order_id}/exceptions", headers=ALICE)).json()[0]
            assert match["invoice_id"] == invoice.id and match["difference_cents"] == 0
            assert ticket["exception_type"] == "MISSING_INVOICE"
            summary = {"batch_id": batch["id"], "matched_count": 1,
                       "unmatched_count": batch["unmatched_count"], "exception_count": 1,
                       "match_ids": [match["id"]], "exception_ids": [ticket["id"]]}
            financial = {name: batch[name] for name in (
                "income_total_cents", "expense_total_cents", "net_cash_change_cents")}
            async with sessions() as session:
                reconciliation_task = await agent_service.create_task(session, AgentTaskCreate(
                    order_id=order_id, agent_role="data_reconciliation", task_type="reconciliation_summary",
                    idempotency_key="summary-v1", correlation_id="flow-1",
                    input_payload={"order_id": order_id, "financial_summary": financial,
                                   "reconciliation_result": summary, "evidence_references": [match["id"]]},
                ))
                summary_fake = FakeAgentGateway({"reconciliation_summary": FakeResult("succeeded", {
                    "narrative_summary": "One exact match", "observations": [],
                    "unresolved_items": [ticket["exception_no"]], "evidence_references": [match["id"]],
                })})
                assert (await agent_service.invoke_task(session, reconciliation_task.id, summary_fake)).status == "succeeded"
                risk_task = await agent_service.create_task(session, AgentTaskCreate(
                    order_id=order_id, agent_role="risk_delivery", task_type="risk_analysis",
                    idempotency_key="risk-v1", correlation_id="flow-1",
                    input_payload={"order_id": order_id, "exception_id": ticket["id"],
                                   "exception_type": ticket["exception_type"], "evidence": ticket["evidence_json"],
                                   "related_amount": ticket["related_amount_cents"],
                                   "difference": ticket["difference_cents"]},
                ))
                risk_fake = FakeAgentGateway({"risk_analysis": FakeResult("paused")})
                assert (await agent_service.invoke_task(session, risk_task.id, risk_fake)).status == "paused"
                await agent_service.save_checkpoint(session, risk_task.run_id, {"phase": "awaiting_context"})
                risk_fake.results["risk_analysis"] = FakeResult("succeeded", {
                    "exception_id": ticket["id"], "preliminary_analysis": "Missing invoice",
                    "customer_questions": ["Can you provide context?"], "unresolved_items": [],
                })
                assert (await agent_service.invoke_task(session, risk_task.id, risk_fake)).status == "succeeded"
                assert risk_task.attempt_count == 2
            assert (await client.post(f"/api/v1/exceptions/{ticket['id']}/decisions", json={
                "decision": "request_supplement", "reason": "Need context", "target_version": 1},
                headers=ALICE)).status_code == 403
            requested = await client.post(f"/api/v1/exceptions/{ticket['id']}/decisions", json={
                "decision": "request_supplement", "reason": "Need context", "target_version": 1},
                headers=OWNER)
            assert requested.status_code == 201
            assert await order_status(client, order_id) == "awaiting_customer"
            added = await client.post(f"/api/v1/exceptions/{ticket['id']}/supplements",
                                      data={"explanation": "Customer deposit for next month"}, headers=ALICE)
            assert added.status_code == 201
            assert await order_status(client, order_id) == "processing"
            accepted = await client.post(f"/api/v1/exceptions/{ticket['id']}/decisions", json={
                "decision": "accept_unresolved", "reason": "Disclose until invoice arrives",
                "target_version": 1}, headers=OWNER)
            assert accepted.status_code == 201
            ticket = (await client.get(f"/api/v1/exceptions/{ticket['id']}", headers=ALICE)).json()
            assert ticket["status"] == "accepted_unresolved"
            async with sessions() as session:
                report_task = await agent_service.create_task(session, AgentTaskCreate(
                    order_id=order_id, agent_role="risk_delivery", task_type="report_draft",
                    idempotency_key="report-v1", correlation_id="flow-1",
                    input_payload={
                        "order_id": order_id, "report_version": 1, "financial_summary": financial,
                        "reconciliation_summary": summary,
                        "exception_summary": [{
                            "exception_id": ticket["id"], "exception_type": ticket["exception_type"],
                            "status": ticket["status"], "related_amount_cents": ticket["related_amount_cents"],
                            "difference_cents": ticket["difference_cents"],
                        }],
                        "evidence_references": [file_id, match["id"], ticket["id"]],
                        "unresolved_items": [ticket["exception_no"]],
                    },
                ))
                report_fake = FakeAgentGateway({"report_draft": FakeResult("succeeded", {
                    "order_id": order_id, "report_version": 1, "report_content": "October monthly report",
                    "evidence_references": [file_id, match["id"], ticket["id"]],
                    "unresolved_items": [ticket["exception_no"]],
                })})
                assert (await agent_service.invoke_task(session, report_task.id, report_fake)).status == "succeeded"
                report = await report_service.create_from_agent_task(session, report_task.id)
                assert report.version == 1 and report.status == "draft"
                assert ticket["exception_no"] in " ".join(report.unresolved_items)
            report_url = f"/api/v1/reports/{report.id}"
            assert (await client.get(report_url, headers=ALICE)).status_code == 404
            assert (await client.post(f"{report_url}/approve", headers=ALICE)).status_code == 403
            assert (await client.post(f"{report_url}/submit-review", headers=OWNER)).status_code == 200
            assert await order_status(client, order_id) == "awaiting_owner_review"
            assert (await client.post(f"{report_url}/approve", headers=OWNER)).status_code == 200
            assert await order_status(client, order_id) == "approved"
            assert (await client.post(f"{report_url}/publish", headers=OWNER)).status_code == 200
            assert await order_status(client, order_id) == "delivered"
            shown = await client.get(report_url, headers=ALICE)
            assert shown.status_code == 200 and shown.json()["version"] == 1
            assert (await client.get(report_url, headers=BOB)).status_code == 404
            assert ticket["exception_no"] in (await client.get(f"{report_url}/download", headers=ALICE)).text
            for kind in ("invoices", "transactions", "matches", "exceptions"):
                exported = await client.get(f"/api/v1/orders/{order_id}/exports/{kind}.csv", headers=ALICE)
                assert exported.status_code == 200 and exported.content.startswith(b"\xef\xbb\xbf")
            async with sessions() as session:
                saved_file = await session.get(UploadedFile, file_id)
                assert LocalStorage(str(storage_root)).read(saved_file.storage_key) == original_image
                saved_transactions = (await session.scalars(select(BankTransaction).where(
                    BankTransaction.order_id == order_id).order_by(BankTransaction.transaction_date))).all()
                assert [item.raw_row_json for item in saved_transactions] == original_rows
                saved_invoice = await session.get(InvoiceRecord, invoice.id)
                assert saved_invoice.source_task_id == extraction.id
                assert (await session.execute(text("PRAGMA foreign_key_check"))).all() == []
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_invoice_amount_failure_rolls_back_without_raw_data_changes(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        content = png_bytes()
        uploaded = await client.post(f"/api/v1/orders/{order_id}/files",
                                     data={"file_category": "invoice_image"},
                                     files=[("files", ("badamount.png", content, "image/png"))], headers=ALICE)
        file_id = uploaded.json()["files"][0]["id"]
        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                review = await agent_service.create_task(session, AgentTaskCreate(
                    order_id=order_id, agent_role="material_review", task_type="material_review",
                    idempotency_key="review", correlation_id="rollback",
                    input_payload={"order_id": order_id, "file_id": file_id,
                                   "file_category": "invoice_image", "mime_type": "image/png"},
                ))
                await agent_service.start_task(session, review.id)
                await agent_service.complete_task(session, review.id, {
                    "file_id": file_id, "review_status": "ACCEPTED", "is_invoice": True,
                    "confidence": 0.9,
                })
                task = await agent_service.create_task(session, AgentTaskCreate(
                    order_id=order_id, agent_role="invoice_processing", task_type="invoice_extraction",
                    idempotency_key="invalid-extraction", correlation_id="rollback",
                    input_payload={"order_id": order_id, "file_id": file_id, "mime_type": "image/png"},
                ))
                await agent_service.start_task(session, task.id)
                await agent_service.complete_task(session, task.id, {
                    "file_id": file_id, "amount": "1.234", "total_amount": "1.234",
                    "confidence": 0.5, "extraction_status": "needs_review",
                })
                try:
                    await persist_invoice_from_task(session, task.id)
                    raise AssertionError("Sub-cent amount must be rejected")
                except AppError as exc:
                    assert exc.code == "invalid_invoice_amount"
                await session.rollback()
                pending = await persist_invoice(session, order_id, InvoiceRecordCreate(
                    source_file_id=file_id, invoice_number="ROLLBACK-1",
                    total_amount_cents=100, extraction_status="ready",
                ))
                assert pending.id is not None
                await session.rollback()
            async with sessions() as session:
                assert (await session.scalars(select(InvoiceRecord).where(InvoiceRecord.order_id == order_id))).all() == []
                assert (await session.execute(text("PRAGMA foreign_key_check"))).all() == []
            assert (await client.get(f"/api/v1/files/{file_id}/download", headers=ALICE)).content == content
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_zip_traversal_and_size_limit_remain_enforced(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        unsafe = await client.post(f"/api/v1/orders/{order_id}/archives",
                                   data={"file_category": "invoice_image"},
                                   files={"file": ("unsafe.zip", zip_bytes({"../escape.png": png_bytes()}),
                                                   "application/zip")}, headers=ALICE)
        assert unsafe.status_code == 422
        assert unsafe.json()["error"]["code"] == "unsafe_archive_path"
        too_large = await client.post(f"/api/v1/orders/{order_id}/files",
                                      data={"file_category": "invoice_image"},
                                      files={"files": ("large.png", b"x" * 101, "image/png")}, headers=ALICE)
        assert too_large.status_code == 413
        assert (await client.get(f"/api/v1/orders/{order_id}/files", headers=BOB)).status_code == 404

    exercise(tmp_path, monkeypatch, scenario, max_image_bytes=100)
