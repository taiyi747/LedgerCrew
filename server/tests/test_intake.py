import io
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from live_support import LiveScriptedRunner
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_live import run_worker
from test_stage2 import exercise

from app.core.exceptions import AppError
from app.db.session import make_engine
from app.intake import service
from app.intake.contracts import PrecheckNarrative
from app.intake.engine import execute_job
from app.live.models import WorkflowRun
from app.models import BankTransaction, InvoiceRecord, Order, ReconciliationBatch, Studio, UploadedFile

ROOT = Path(__file__).resolve().parents[2] / "fixtures/mvp"
CUSTOMER = {"X-User-Id": "alice"}
OWNER = {"X-User-Id": "owner"}


def packed(extra=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for i in range(1, 7):
            z.writestr(f"invoices/receipt-{i:02}.png", (ROOT / f"receipt-{i:02}.png").read_bytes())
        z.writestr("statement.csv", (ROOT / "statement-live.csv").read_bytes())
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return out.getvalue()


async def prepare(client, *, extra=None, profile=True, csv_only=False):
    r = await client.post("/api/v1/intakes", headers=CUSTOMER, json={})
    assert r.status_code == 201, r.text
    item = r.json()
    iid = item["id"]
    if profile:
        r = await client.patch(
            f"/api/v1/intakes/{iid}",
            headers=CUSTOMER,
            json={
                "expected_revision": item["revision"],
                "studio_name": "松石设计工作室",
                "period_start": "2026-10-01",
                "period_end": "2026-10-31",
            },
        )
        assert r.status_code == 200, r.text
        item = r.json()
    payload = (ROOT / "statement-live.csv").read_bytes() if csv_only else packed(extra)
    r = await client.post(
        f"/api/v1/intakes/{iid}/files",
        headers=CUSTOMER,
        data={"expected_revision": item["revision"]},
        files={
            "files": (
                "statement.csv" if csv_only else "materials.zip",
                payload,
                "text/csv" if csv_only else "application/zip",
            )
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def check(client, item):
    r = await client.post(
        f"/api/v1/intakes/{item['id']}/prechecks",
        headers=CUSTOMER,
        json={"expected_revision": item["revision"]},
    )
    assert r.status_code == 202, r.text
    return r.json()


async def execute(job_id, runner=None, raise_errors=True):
    engine = make_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        token = str(uuid4())
        async with sessions() as s:
            assert await service.claim(s, job_id, token)
        await execute_job(
            sessions, job_id, token, runner=runner or LiveScriptedRunner(), raise_errors=raise_errors
        )
    finally:
        await engine.dispose()


async def snapshot(client, item):
    return (await client.get(f"/api/v1/intakes/{item['id']}", headers=CUSTOMER)).json()


def confirmation(item):
    return {
        "expected_revision": item["revision"],
        "precheck_id": item["precheck"]["id"],
        "service_version": 1,
        "idempotency_key": "confirm-once",
        "acknowledged_warning_ids": [w["id"] for w in item["confirmation"]["warnings"]],
    }


async def count(models):
    engine = make_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        result = [await s.scalar(select(func.count()).select_from(m)) for m in models]
    await engine.dispose()
    return result


def test_intake_zip_to_actual_order_delivery(tmp_path, monkeypatch):
    async def scenario(client, _):
        item = await prepare(client)
        assert len(item["files"]) == 8
        job = await check(client, item)
        runner = LiveScriptedRunner()
        await execute(job["id"], runner)
        item = await snapshot(client, item)
        iid = item["id"]
        assert item["status"] == "ready_with_warnings"
        assert len(item["precheck"]["result"]["sampled_file_ids"]) == 3
        assert len([c for c in runner.calls if c[1] == "ImageSample"]) == 3
        assert not any(c[1] == "InvoiceExtractionOutput" for c in runner.calls)
        assert await count([Order, InvoiceRecord, ReconciliationBatch, BankTransaction]) == [0, 0, 0, 0]
        assert (await check(client, item))["id"] == job["id"]
        body = confirmation(item)
        assert (
            await client.post(
                f"/api/v1/intakes/{iid}/confirm",
                headers=CUSTOMER,
                json={**body, "acknowledged_warning_ids": []},
            )
        ).status_code == 422
        r = await client.post(f"/api/v1/intakes/{iid}/confirm", headers=CUSTOMER, json=body)
        assert r.status_code == 201, r.text
        again = await client.post(f"/api/v1/intakes/{iid}/confirm", headers=CUSTOMER, json=body)
        assert again.json() == r.json()
        oid = r.json()["order_id"]
        orders = (await client.get("/api/v1/orders", headers=CUSTOMER)).json()
        assert len(orders) == 1 and orders[0]["price_cents"] == 1990 and orders[0]["intake_id"] == iid
        assert await count([BankTransaction]) == [6]
        await run_worker(tmp_path, LiveScriptedRunner())
        batch = (await client.get(f"/api/v1/orders/{oid}/reconciliation", headers=CUSTOMER)).json()
        assert batch["matched_count"] == 4 and batch["exception_count"] == 3
        tickets = (await client.get(f"/api/v1/orders/{oid}/exceptions", headers=CUSTOMER)).json()
        assert (
            next(t for t in tickets if t["exception_type"] == "AMOUNT_MISMATCH")["difference_cents"] == 27000
        )
        for t in tickets:
            r = await client.post(
                f"/api/v1/exceptions/{t['id']}/decisions",
                headers=OWNER,
                json={"decision": "accept_unresolved", "reason": "保留未解决事项", "target_version": 1},
            )
            assert r.status_code == 201, r.text
        await run_worker(tmp_path, LiveScriptedRunner())
        report = (await client.get(f"/api/v1/orders/{oid}/reports", headers=OWNER)).json()[0]
        assert (await client.get(f"/api/v1/reports/{report['id']}", headers=CUSTOMER)).status_code == 404
        for action in ("submit-review", "approve", "publish"):
            r = await client.post(
                f"/api/v1/reports/{report['id']}/{action}", headers=OWNER, json={"reason": "确认本版本"}
            )
            assert r.status_code == 200, r.text
        await run_worker(tmp_path, LiveScriptedRunner())
        assert (await client.get(f"/api/v1/orders/{oid}/runs/current", headers=CUSTOMER)).json()[
            "status"
        ] == "succeeded"
        assert (
            await client.get(f"/api/v1/reports/{report['id']}/download", headers=CUSTOMER)
        ).status_code == 200

    exercise(tmp_path, monkeypatch, scenario)


def test_exclusion_revision_permissions_and_sse(tmp_path, monkeypatch):
    async def scenario(client, _):
        item = await prepare(client, extra={"notes/readme.pdf": b"%PDF-unsupported"})
        iid = item["id"]
        f = next(f for f in item["files"] if f["original_filename"] == "readme.pdf")
        job = await check(client, item)
        endpoint = f"/api/v1/intakes/{iid}/files/{f['id']}"
        assert (
            await client.patch(
                endpoint, headers=CUSTOMER, json={"expected_revision": item["revision"], "included": False}
            )
        ).status_code == 409
        await execute(job["id"])
        item = await snapshot(client, item)
        assert item["status"] == "needs_info" and item["confirmation"] is None
        r = await client.patch(
            endpoint, headers=CUSTOMER, json={"expected_revision": item["revision"], "included": False}
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["precheck"]["result"] is None
        assert (
            await client.patch(
                endpoint, headers=CUSTOMER, json={"expected_revision": item["revision"], "included": True}
            )
        ).status_code == 409
        job = await check(client, updated)
        await execute(job["id"])
        updated = await snapshot(client, updated)
        assert updated["confirmation"]
        for path in [
            f"/api/v1/intakes/{iid}",
            f"/api/v1/intakes/{iid}/files/{f['id']}/download",
            f"/api/v1/intakes/{iid}/events/stream?follow=false",
        ]:
            assert (await client.get(path, headers={"X-User-Id": "bob"})).status_code == 404
        assert (await client.get("/api/v1/owner/intakes", headers=CUSTOMER)).status_code == 403
        assert (await client.get("/api/v1/owner/intakes", headers=OWNER)).status_code == 200
        assert (
            await client.post(
                f"/api/v1/intakes/{iid}/confirm",
                headers=CUSTOMER,
                json={**confirmation(updated), "precheck_id": item["precheck"]["id"]},
            )
        ).status_code == 409
        frames = (
            await client.get(f"/api/v1/intakes/{iid}/events/stream?follow=false", headers=CUSTOMER)
        ).text
        assert "precheck.completed" in frames
        last = int([line for line in frames.splitlines() if line.startswith("id: ")][-1][4:])
        assert (
            await client.get(
                f"/api/v1/intakes/{iid}/events/stream?follow=false&after_id={last}", headers=CUSTOMER
            )
        ).text == ""

    exercise(tmp_path, monkeypatch, scenario)


def test_confirmation_atomic_rollback(tmp_path, monkeypatch):
    async def scenario(client, _):
        item = await prepare(client)
        job = await check(client, item)
        await execute(job["id"])
        item = await snapshot(client, item)
        endpoint = f"/api/v1/intakes/{item['id']}/confirm"
        body = confirmation(item)
        assert (
            await client.post(endpoint, headers=CUSTOMER, json={**body, "price_cents": 1})
        ).status_code == 422
        real = service.live.start_run

        async def fail(*args, **kwargs):
            raise AppError("forced", "模拟确认事务末尾失败", 409)

        monkeypatch.setattr(service.live, "start_run", fail)
        r = await client.post(endpoint, headers=CUSTOMER, json=body)
        assert r.status_code == 409, r.text
        assert await count([Order, Studio, UploadedFile, BankTransaction, WorkflowRun]) == [0, 0, 0, 0, 0]
        assert (await snapshot(client, item))["order_id"] is None
        monkeypatch.setattr(service.live, "start_run", real)
        r = await client.post(endpoint, headers=CUSTOMER, json=body)
        assert r.status_code == 201, r.text

    exercise(tmp_path, monkeypatch, scenario)


def test_precheck_restart_preserves_samples_and_budget(tmp_path, monkeypatch):
    async def scenario(client, _):
        item = await prepare(client)
        job = await check(client, item)

        class Interrupted(LiveScriptedRunner):
            async def generate(self, role, prompt, schema, budget, **kw):
                if schema is PrecheckNarrative:
                    await budget.reserve()
                    tools = {t.__name__: t for t in kw["tools"]}
                    await tools["inspect_intake_materials"]()

                    raise RuntimeError("模拟抽查完成后执行中断")
                return await super().generate(role, prompt, schema, budget, **kw)

        await execute(job["id"], Interrupted(), raise_errors=False)
        failed = await snapshot(client, item)
        assert failed["precheck"]["requests_used"] == 4 and failed["status"] == "precheck_failed"
        again = await check(client, failed)
        assert again["id"] == job["id"] and again["requests_used"] == 4
        runner = LiveScriptedRunner()
        await execute(job["id"], runner)
        assert not any(name == "ImageSample" for _, name in runner.calls)
        done = await snapshot(client, item)
        assert done["precheck"]["requests_used"] == 5 and done["confirmation"]

    exercise(tmp_path, monkeypatch, scenario)


def test_csv_only_profile_and_archive_rejections(tmp_path, monkeypatch):
    async def scenario(client, _):
        item = await prepare(client, csv_only=True, profile=False)
        job = await check(client, item)
        await execute(job["id"])
        item = await snapshot(client, item)
        assert any(i["code"] == "profile_required" for i in item["precheck"]["result"]["blockers"])
        r = await client.patch(
            f"/api/v1/intakes/{item['id']}",
            headers=CUSTOMER,
            json={
                "expected_revision": item["revision"],
                "studio_name": "无票据商户",
                "period_start": "2026-10-01",
                "period_end": "2026-10-31",
            },
        )
        item = r.json()
        job = await check(client, item)
        await execute(job["id"])
        item = await snapshot(client, item)
        assert item["confirmation"]["warnings"][0]["code"] == "no_invoices"
        r = await client.post(
            f"/api/v1/intakes/{item['id']}/confirm", headers=CUSTOMER, json=confirmation(item)
        )
        assert r.status_code == 201, r.text
        bad = (await client.post("/api/v1/intakes", headers=CUSTOMER, json={})).json()
        for data in [b"broken zip", packed({"../bad.png": b"unsafe"}), packed({"nested.zip": b"PK\x03\x04"})]:
            r = await client.post(
                f"/api/v1/intakes/{bad['id']}/files",
                headers=CUSTOMER,
                data={"expected_revision": 1},
                files={"files": ("bad.zip", data, "application/zip")},
            )
            assert r.status_code == 422, r.text
            assert (await snapshot(client, bad))["files"] == []

    exercise(tmp_path, monkeypatch, scenario)


def test_concurrent_confirmation_only_creates_one_order(tmp_path, monkeypatch):
    async def scenario(client, _):
        import asyncio

        item = await prepare(client)
        job = await check(client, item)
        await execute(job["id"])
        item = await snapshot(client, item)
        url = f"/api/v1/intakes/{item['id']}/confirm"
        body = confirmation(item)
        a, b = await asyncio.gather(
            client.post(url, headers=CUSTOMER, json=body),
            client.post(url, headers=CUSTOMER, json={**body, "idempotency_key": "second-click"}),
        )
        assert a.status_code == b.status_code == 201, (a.text, b.text)
        assert a.json()["order_id"] == b.json()["order_id"]
        assert await count([Order, BankTransaction, WorkflowRun]) == [1, 6, 1]

    exercise(tmp_path, monkeypatch, scenario)


def test_csv_errors_block_and_owner_cannot_edit(tmp_path, monkeypatch):
    async def scenario(client, _):
        item = await prepare(client, csv_only=True)
        iid = item["id"]
        old = item["files"][0]
        r = await client.patch(
            f"/api/v1/intakes/{iid}/files/{old['id']}",
            headers=OWNER,
            json={"expected_revision": item["revision"], "included": False},
        )
        assert r.status_code == 403
        r = await client.patch(
            f"/api/v1/intakes/{iid}/files/{old['id']}",
            headers=CUSTOMER,
            json={"expected_revision": item["revision"], "included": False},
        )
        item = r.json()
        bad = b"transaction_date,counterparty,direction,amount\n2026-10-01,Store,OUT,invalid\n"
        r = await client.post(
            f"/api/v1/intakes/{iid}/files",
            headers=CUSTOMER,
            data={"expected_revision": item["revision"]},
            files={"files": ("bad.csv", bad, "text/csv")},
        )
        item = r.json()
        job = await check(client, item)
        await execute(job["id"])
        item = await snapshot(client, item)
        assert item["confirmation"] is None
        assert any(b["code"] == "csv_rows_invalid" for b in item["precheck"]["result"]["blockers"])
        assert item["precheck"]["result"]["csv_details"][0]["errors"][0]["row_number"] == 2
        assert await count([Order, BankTransaction]) == [0, 0]

    exercise(tmp_path, monkeypatch, scenario)


def test_unexecuted_tools_never_pass_precheck(tmp_path, monkeypatch):
    async def scenario(client, _):
        class Liar:
            async def generate(self, role, prompt, schema, budget, **kw):
                await budget.reserve()
                return PrecheckNarrative(summary="宣称已完成全部检查", questions=[], evidence_refs=[])

        item = await prepare(client, csv_only=True)
        job = await check(client, item)
        await execute(job["id"], Liar(), raise_errors=False)
        item = await snapshot(client, item)
        assert item["status"] == "precheck_failed" and item["confirmation"] is None
        assert item["precheck"]["requests_used"] == 3
        assert await count([Order]) == [0]

    exercise(tmp_path, monkeypatch, scenario)


def test_shared_queue_and_expired_lease(tmp_path, monkeypatch):
    async def scenario(client, _):
        from datetime import timedelta

        from test_stage2 import create_order

        from app.agents.errors import AgentError
        from app.db.types import utc_now
        from app.intake.engine import IntakeBudgetStore
        from app.intake.models import IntakeJob
        from app.live.worker import claim_slot

        _, oid = await create_order(client)
        item = await prepare(client, csv_only=True)
        job = await check(client, item)
        engine = make_engine()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as s:
                legacy = WorkflowRun(
                    order_id=oid,
                    kind="processing",
                    status="queued",
                    stage="supervisor",
                    input_revision=1,
                    idempotency_key="queue-test",
                    created_by="alice",
                    created_at=utc_now() - timedelta(minutes=1),
                )
                s.add(legacy)
                await s.commit()
                work = await claim_slot(s, "processing", "first-token")
                assert work == ("order", legacy.id)
                legacy.status = "succeeded"
                legacy.lease_token = None
                await s.commit()
                assert await claim_slot(s, "processing", "old-token") == ("intake", job["id"])
                j = await s.get(IntakeJob, job["id"])
                j.lease_expires_at = utc_now() - timedelta(seconds=1)
                await s.commit()
            store = IntakeBudgetStore(sessions, job["id"], "old-token")
            with pytest.raises(AgentError):
                await store.load_artifact(None, "usage")
            async with sessions() as s:
                assert await service.claim(s, job["id"], "new-token")
            with pytest.raises(AgentError):
                await store.load_artifact(None, "usage")
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_queued_intake_reply_follows_confirmed_order(tmp_path, monkeypatch):
    async def scenario(client, _):
        item = await prepare(client, csv_only=True)
        job = await check(client, item)
        await execute(job["id"])
        item = await snapshot(client, item)
        data = {"client_message_id": "one-message", "content": "这项服务包含哪些交付？"}
        reply = await client.post(f"/api/v1/intakes/{item['id']}/messages", headers=CUSTOMER, json=data)
        repeated = await client.post(f"/api/v1/intakes/{item['id']}/messages", headers=CUSTOMER, json=data)
        assert reply.json() == repeated.json()
        r = await client.post(
            f"/api/v1/intakes/{item['id']}/confirm", headers=CUSTOMER, json=confirmation(item)
        )
        assert r.status_code == 201, r.text
        await execute(reply.json()["job_id"])
        messages = (
            await client.get(f"/api/v1/orders/{r.json()['order_id']}/messages", headers=CUSTOMER)
        ).json()
        assert any(m["content"].startswith("请上传材料并确认工作室") for m in messages)

    exercise(tmp_path, monkeypatch, scenario)


def test_saved_tool_result_survives_final_model_ack_failure(tmp_path, monkeypatch):
    async def scenario(client, _):
        from app.agents.errors import AgentError

        class SavedThenFailed(LiveScriptedRunner):
            async def generate(self, role, prompt, schema, budget, **kw):
                value = await super().generate(role, prompt, schema, budget, **kw)
                if schema is PrecheckNarrative:
                    raise AgentError("模拟成果保存后的模型确认失败")
                return value

        item = await prepare(client)
        job = await check(client, item)
        await execute(job["id"], SavedThenFailed())
        done = await snapshot(client, item)
        assert done["confirmation"] and done["precheck"]["requests_used"] == 5
        assert await count([Order, InvoiceRecord, ReconciliationBatch]) == [0, 0, 0]

    exercise(tmp_path, monkeypatch, scenario)


def test_precheck_usage_can_exceed_twelve_without_stopping(tmp_path, monkeypatch):
    async def scenario(client, _):
        from app.agents.contracts import RunIdentity
        from app.agents.runner import RequestBudget
        from app.intake.engine import IntakeBudgetStore
        from app.intake.models import IntakeJob

        item = await prepare(client, csv_only=True)
        job = await check(client, item)
        engine = make_engine()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as s:
                assert await service.claim(s, job["id"], "token")
            store = IntakeBudgetStore(sessions, job["id"], "token")
            budget = RequestBudget(
                store,
                RunIdentity(order_id="intake_" + item["id"], run_id=job["id"], revision=item["revision"]),
                None,
            )
            for _ in range(14):
                await budget.reserve()
            async with sessions() as s:
                current = await s.get(IntakeJob, job["id"])
                assert current.requests_used == 14 and current.request_limit is None
                current.status = "failed"
                current.lease_token = None
                await s.commit()
            again = await check(client, item)
            assert again["requests_used"] == 14 and again["request_limit"] is None
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_repeated_checks_without_progress_stop_explicitly(tmp_path, monkeypatch):
    async def scenario(client, _):
        class Repeating(LiveScriptedRunner):
            async def generate(self, role, prompt, schema, budget, **kw):
                if schema is PrecheckNarrative:
                    await budget.reserve()
                    tool = next(t for t in kw["tools"] if t.__name__ == "inspect_intake_materials")
                    for _ in range(4):
                        await tool()
                return await super().generate(role, prompt, schema, budget, **kw)

        item = await prepare(client)
        job = await check(client, item)
        await execute(job["id"], Repeating(), raise_errors=False)
        failed = await snapshot(client, item)
        assert failed["status"] == "precheck_failed" and failed["confirmation"] is None
        assert await count([Order]) == [0]

    exercise(tmp_path, monkeypatch, scenario)
