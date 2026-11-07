"""Real backend order through the existing MAF graph, human pauses and report."""

from pathlib import Path

from agents.support import ScriptedRunner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import create_order, exercise

from app.agents.config import Settings as MiMoSettings
from app.core.config import get_settings
from app.db.session import make_engine
from app.integrations.agents.fake_gateway import FakeAgentGateway
from app.integrations.agents.workflow_gateway import FullWorkflowGateway, RoutedAgentGateway
from app.models import AgentModelArtifact, AgentTask, ReconciliationBatch, ReportVersion
from app.storage.local import LocalStorage
from scripts.run_agent_tasks import run_once

FIXTURES = Path(__file__).parents[2] / "fixtures" / "mvp"


def test_order_to_maf_review_and_approved_report(tmp_path, monkeypatch) -> None:
    async def scenario(client, storage_path) -> None:
        _, order_id = await create_order(client)
        alice = {"X-User-Id": "alice"}
        owner = {"X-User-Id": "owner"}
        image = (FIXTURES / "receipt-01.png").read_bytes()
        uploaded = await client.post(
            f"/api/v1/orders/{order_id}/files", data={"file_category": "invoice_image"},
            files=[("files", ("receipt.png", image, "image/png"))], headers=alice)
        assert uploaded.status_code == 201, uploaded.text
        csv = b"transaction_date,counterparty,direction,amount\n2026-10-10,Other,out,1.00\n"
        uploaded_csv = await client.post(
            f"/api/v1/orders/{order_id}/files", data={"file_category": "bank_statement_csv"},
            files=[("files", ("statement.csv", csv, "text/csv"))], headers=alice)
        assert uploaded_csv.status_code == 201, uploaded_csv.text
        created = await client.post(f"/api/v1/orders/{order_id}/workflows",
                                    headers={**alice, "Idempotency-Key": "full-flow-1"})
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        duplicate = await client.post(f"/api/v1/orders/{order_id}/workflows",
                                      headers={**alice, "Idempotency-Key": "full-flow-1"})
        assert duplicate.json()["id"] == task_id

        engine = make_engine(get_settings().database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        gateway = RoutedAgentGateway(
            FakeAgentGateway({}), FullWorkflowGateway(
                sessions, LocalStorage(str(storage_path)), storage_path / "workflow_checkpoints",
                MiMoSettings(api_key="test-only"), ScriptedRunner(FIXTURES)))
        try:
            assert await run_once(sessions, gateway)
            pending = await client.get(f"/api/v1/agent-tasks/{task_id}/workflow-review", headers=owner)
            assert pending.status_code == 200, pending.text
            assert pending.json()["request"]["kind"] == "exception"
            assert pending.json()["report_id"] is None
            assert (await client.get(f"/api/v1/agent-tasks/{task_id}/workflow-review",
                                     headers=alice)).status_code == 403
            replied = await client.post(f"/api/v1/agent-tasks/{task_id}/workflow-reply",
                                        json={"action": "keep_flagged", "comment": "保留异常"}, headers=owner)
            assert replied.status_code == 200, replied.text
            assert replied.json()["status"] == "retrying"
            assert await run_once(sessions, gateway)
            pending = (await client.get(f"/api/v1/agent-tasks/{task_id}/workflow-review",
                                        headers=owner)).json()
            assert pending["request"]["kind"] == "delivery"
            report_id = pending["report_id"]
            assert report_id
            duplicate_after_pause = await client.post(
                f"/api/v1/orders/{order_id}/workflows",
                headers={**alice, "Idempotency-Key": "full-flow-1"})
            assert duplicate_after_pause.status_code == 201
            assert duplicate_after_pause.json()["id"] == task_id
            assert (await client.post(f"/api/v1/reports/{report_id}/approve", headers=owner)).status_code == 409
            rejected_reply = await client.post(f"/api/v1/agent-tasks/{task_id}/workflow-reply",
                                               json={"action": "revise_report", "comment": "",
                                                     "report_version": pending["request"]["report_version"]},
                                               headers=owner)
            assert rejected_reply.status_code == 422
            assert (await client.get(f"/api/v1/agent-tasks/{task_id}/workflow-review",
                                     headers=owner)).status_code == 200
            approval = await client.post(f"/api/v1/agent-tasks/{task_id}/workflow-reply",
                                         json={"action": "approve_delivery",
                                               "report_version": pending["request"]["report_version"]},
                                         headers=owner)
            assert approval.status_code == 200, approval.text
            assert await run_once(sessions, gateway)
            async with sessions() as db:
                task = await db.get(AgentTask, task_id)
                report = await db.get(ReportVersion, report_id)
                batch = await db.scalar(select(ReconciliationBatch).where(
                    ReconciliationBatch.workflow_task_id == task_id))
                assert task.status == "succeeded" and task.output_data["report_id"] == report_id
                assert report.status == "approved" and report.approved_by == "owner"
                assert report.reconciliation_batch_id == batch.id
                assert report.unresolved_items
                artifacts = (await db.scalars(select(AgentModelArtifact).where(
                    AgentModelArtifact.task_id == task_id))).all()
                assert any(item.kind == "usage" for item in artifacts)
            order = await client.get(f"/api/v1/orders/{order_id}", headers=alice)
            assert order.json()["status"] == "approved"
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)
