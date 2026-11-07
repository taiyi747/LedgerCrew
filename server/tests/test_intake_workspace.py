import io
import json

import pytest
from live_support import LiveScriptedRunner
from openpyxl import Workbook
from pypdf import PdfWriter
from test_intake import CUSTOMER, check, count, execute, prepare, snapshot
from test_stage2 import exercise

from app.intake.contracts import PrecheckNarrative
from app.models import InvoiceRecord, Order, ReconciliationBatch


class WorkspaceRunner(LiveScriptedRunner):
    async def generate(self, role, prompt, schema, budget, **kw):
        if schema is PrecheckNarrative:
            tools = {tool.__name__: tool for tool in kw["tools"]}
            original = tools["inspect_intake_materials"]

            async def finish_workspace():
                files = json.loads(await tools["list_materials"]())
                tasks = []
                for file in files:
                    if not file["included"] or file["source_file_id"]:
                        continue
                    tasks.append(
                        {"file_id": file["id"], "kind": "read_document", "title": "读取 " + file["name"]}
                    )
                    if file["name"].endswith((".xlsx", "原始流水.csv")):
                        tasks.append(
                            {"file_id": file["id"], "kind": "normalize_statement", "title": "整理原始流水"}
                        )
                    if file["name"].endswith(".pdf"):
                        tasks.append(
                            {"file_id": file["id"], "kind": "prepare_receipts", "title": "准备 PDF 票据页"}
                        )
                tasks.append({"file_id": "", "kind": "check_materials", "title": "确认服务启动条件"})
                await tools["plan_materials"](tasks)
                for file in files:
                    if file["name"].endswith((".xlsx", "原始流水.csv")):
                        mapping = {
                            "transaction_date": "交易日期",
                            "counterparty": "对方户名",
                            "direction": "收支",
                            "amount": "发生额",
                        }
                        result = json.loads(await tools["normalize_statement"](file["id"], mapping))
                        assert "error" not in result, result
                        again = json.loads(await tools["normalize_statement"](file["id"], mapping))
                        assert again["file_id"] == result["file_id"]
                    if file["name"].endswith(".pdf"):
                        result = json.loads(await tools["prepare_pdf_receipts"](file["id"], [1]))
                        assert "error" not in result, result
                return await original()

            finish_workspace.__name__ = "inspect_intake_materials"
            kw["tools"] = [
                finish_workspace if t.__name__ == "inspect_intake_materials" else t for t in kw["tools"]
            ]
        return await super().generate(role, prompt, schema, budget, **kw)


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_original_table_normalizes_without_customer_template(tmp_path, monkeypatch, extension):
    async def scenario(client, _):
        item = await prepare(client, csv_only=True)
        old = item["files"][0]
        response = await client.patch(
            f"/api/v1/intakes/{item['id']}/files/{old['id']}",
            headers=CUSTOMER,
            json={"expected_revision": item["revision"], "included": False},
        )
        item = response.json()
        rows = [
            ["交易日期", "对方户名", "收支", "发生额"],
            ["2026/10/08", "松石测试供应商", "支出", "1,280.50"],
        ]
        if extension == "xlsx":
            workbook = Workbook()
            for row in rows:
                workbook.active.append(row)
            stream = io.BytesIO()
            workbook.save(stream)
            content = stream.getvalue()
        else:
            import csv

            stream = io.StringIO()
            csv.writer(stream).writerows(rows)
            content = stream.getvalue().encode("utf-8-sig")
        response = await client.post(
            f"/api/v1/intakes/{item['id']}/files",
            headers=CUSTOMER,
            data={"expected_revision": item["revision"]},
            files={"files": ("原始流水." + extension, content, "application/octet-stream")},
        )
        assert response.status_code == 201, response.text
        item = response.json()
        source = next(f for f in item["files"] if f["included"])
        job = await check(client, item)
        await execute(job["id"], WorkspaceRunner())
        done = await snapshot(client, item)
        assert done["confirmation"]
        generated = [f for f in done["files"] if f["derived_from_file_id"] == source["id"]]
        assert len(generated) == 1
        assert generated[0]["category"] == "bank_statement_csv" and generated[0]["included"]
        download = await client.get(
            f"/api/v1/intakes/{item['id']}/files/{generated[0]['id']}/download", headers=CUSTOMER
        )
        assert "1280.50" in download.content.decode("utf-8-sig")
        assert all(t["status"] == "completed" for t in done["precheck"]["todos"])
        assert await count([Order, InvoiceRecord, ReconciliationBatch]) == [0, 0, 0]

    exercise(tmp_path, monkeypatch, scenario)


def test_pdf_receipts_become_traceable_images(tmp_path, monkeypatch):
    async def scenario(client, _):
        item = await prepare(client, csv_only=True)
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=200)
        stream = io.BytesIO()
        writer.write(stream)
        response = await client.post(
            f"/api/v1/intakes/{item['id']}/files",
            headers=CUSTOMER,
            data={"expected_revision": item["revision"]},
            files={"files": ("票据.pdf", stream.getvalue(), "application/pdf")},
        )
        assert response.status_code == 201
        item = response.json()
        source = next(f for f in item["files"] if f["original_filename"] == "票据.pdf")
        job = await check(client, item)
        await execute(job["id"], WorkspaceRunner())
        done = await snapshot(client, item)
        assert done["confirmation"]
        page = next(f for f in done["files"] if f["derived_from_file_id"] == source["id"])
        assert page["mime_type"] == "image/png" and page["included"]
        original = next(f for f in done["files"] if f["id"] == source["id"])
        assert not original["included"]
        assert await count([InvoiceRecord, ReconciliationBatch]) == [0, 0]

    exercise(tmp_path, monkeypatch, scenario)


def test_unknown_file_is_received_but_cannot_be_claimed_as_read(tmp_path, monkeypatch):
    async def scenario(client, _):
        item = await prepare(client, csv_only=True)
        response = await client.post(
            f"/api/v1/intakes/{item['id']}/files",
            headers=CUSTOMER,
            data={"expected_revision": item["revision"]},
            files={"files": ("原始导出.unknown", b"unrecognized binary", "application/octet-stream")},
        )
        assert response.status_code == 201
        item = response.json()
        job = await check(client, item)
        await execute(job["id"])
        done = await snapshot(client, item)
        assert done["confirmation"] is None
        assert any(t["status"] == "blocked" for t in done["precheck"]["todos"])
        assert any(b["code"] == "workspace_blocked" for b in done["precheck"]["result"]["blockers"])

    exercise(tmp_path, monkeypatch, scenario)


def test_workspace_cannot_read_another_intake_or_host_path(tmp_path, monkeypatch):
    async def scenario(client, _):
        other = await prepare(client, csv_only=True)
        foreign_id = other["files"][0]["id"]

        class OutsideReader(LiveScriptedRunner):
            async def generate(self, role, prompt, schema, budget, **kw):
                if schema is PrecheckNarrative:
                    tools = {tool.__name__: tool for tool in kw["tools"]}
                    for forbidden in [foreign_id, "../../.env"]:
                        plan = json.loads(
                            await tools["plan_materials"](
                                [{"file_id": forbidden, "kind": "read_document", "title": "读取外部文件"}]
                            )
                        )
                        assert "error" in plan
                        result = json.loads(await tools["read_document"](forbidden))
                        assert "error" in result
                return await super().generate(role, prompt, schema, budget, **kw)

        item = await prepare(client, csv_only=True)
        job = await check(client, item)
        await execute(job["id"], OutsideReader())
        done = await snapshot(client, item)
        assert done["confirmation"]
        assert not any(t["file_id"] == foreign_id for t in done["precheck"]["todos"])

    exercise(tmp_path, monkeypatch, scenario)
