"""BE2-10-12：审批失效、工作流恢复与幂等回归测试（MVP 机制层面）。

P2 的 FilingTask / TaxReturnDraft / TaxCalculation / FilingPackage / ApprovalRecord 尚未实现，
本文件不新增任何业务规则，只在 MVP 已有的 ReportVersion、ReportReviewAction、AgentTask、
AgentRun、WorkflowEvent、AuditLog 与检查点机制上验证既有技术安全边界，并为 P2 场景留出回归骨架。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import create_order, exercise, png_bytes
from test_stage3 import upload_csv
from test_stage5 import reception_output, reception_task
from test_stage6 import make_batch_with_exception

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import Principal
from app.db.session import make_engine
from app.integrations.agents.fake_gateway import FakeAgentGateway, FakeResult
from app.models import AgentRun, AgentTask, AuditLog, Order, ReportReviewAction, ReportVersion, WorkflowEvent
from app.schemas.agent import AgentTaskCreate
from app.services import agent_service, order_state, report_service

ALICE = {"X-User-Id": "alice"}
BOB = {"X-User-Id": "bob"}
OWNER = {"X-User-Id": "owner"}

EXTRA_CSV = (b"transaction_date,counterparty,direction,amount,description,external_id\n"
             b"2026-10-20,NewVendor,OUT,3.00,late service,tx-3\n")


def _sessions():
    engine = make_engine(get_settings().database_url)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def fetch_context(client, order_id: str):
    batch = (await client.get(f"/api/v1/orders/{order_id}/reconciliation", headers=ALICE)).json()
    tickets = (await client.get(f"/api/v1/orders/{order_id}/exceptions", headers=ALICE)).json()
    matches = (await client.get(f"/api/v1/orders/{order_id}/matches", headers=ALICE)).json()
    return batch, tickets, matches


def report_task_payload(order_id: str, batch: dict, tickets: list, matches: list, version: int,
                        idempotency_key: str | None = None) -> AgentTaskCreate:
    summary = {name: batch[name] for name in ("matched_count", "unmatched_count", "exception_count")}
    summary.update({"batch_id": batch["id"], "match_ids": [item["id"] for item in matches],
                    "exception_ids": [item["id"] for item in tickets]})
    financial = {name: batch[name] for name in (
        "income_total_cents", "expense_total_cents", "net_cash_change_cents")}
    exception_summary = [{
        "exception_id": item["id"], "exception_type": item["exception_type"], "status": item["status"],
        "related_amount_cents": item["related_amount_cents"], "difference_cents": item["difference_cents"],
    } for item in tickets]
    return AgentTaskCreate(
        order_id=order_id, agent_role="risk_delivery", task_type="report_draft",
        idempotency_key=idempotency_key or f"be2-10-12-report-v{version}",
        correlation_id=f"be2-10-12-report-{version}",
        input_payload={"order_id": order_id, "report_version": version,
                       "financial_summary": financial, "reconciliation_summary": summary,
                       "exception_summary": exception_summary,
                       "evidence_references": [], "unresolved_items": []},
    )


def report_output(order_id: str, version: int, content: str) -> dict:
    return {"order_id": order_id, "report_version": version, "report_content": content,
            "evidence_references": [], "unresolved_items": []}


async def create_report(client, order_id: str, version: int, content: str) -> ReportVersion:
    """Agent 产出草稿的可信集成入口：任务校验与审批仍全部走既有服务。"""
    batch, tickets, matches = await fetch_context(client, order_id)
    engine, sessions = _sessions()
    try:
        async with sessions() as session:
            task = await agent_service.create_task(
                session, report_task_payload(order_id, batch, tickets, matches, version))
            await agent_service.start_task(session, task.id)
            await agent_service.complete_task(session, task.id, report_output(order_id, version, content))
            return await report_service.create_from_agent_task(session, task.id)
    finally:
        await engine.dispose()


async def change_data_and_rerun(client, order_id: str) -> dict:
    """修改输入数据并重新对账，产生新的数据版本（新 batch）。"""
    csv_id = await upload_csv(client, order_id, EXTRA_CSV)
    imported = await client.post(f"/api/v1/orders/{order_id}/imports/csv",
                                 json={"file_id": csv_id}, headers=ALICE)
    assert imported.status_code == 201, imported.text
    rerun = await client.post(f"/api/v1/orders/{order_id}/reconciliation/run", headers=ALICE)
    assert rerun.status_code == 201, rerun.text
    return rerun.json()


# ---------------------------------------------------------------- 审批失效与版本变化


def test_v1_approval_never_transfers_to_v2_and_history_is_preserved(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        await make_batch_with_exception(client, order_id)
        v1 = await create_report(client, order_id, 1, "V1 申报说明")
        v1_url = f"/api/v1/reports/{v1.id}"
        assert (await client.post(f"{v1_url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{v1_url}/approve", headers=OWNER)).status_code == 200

        # 修改输入数据 → 新数据版本
        first_batch, _, _ = await fetch_context(client, order_id)
        second_batch = await change_data_and_rerun(client, order_id)
        assert second_batch["id"] != first_batch["id"]

        # V1 审批随输入变化失效，已批准的 V1 不能发布
        stale = await client.post(f"{v1_url}/publish", headers=OWNER)
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_report"

        # 生成 V2
        v2 = await create_report(client, order_id, 2, "V2 申报说明")
        v2_url = f"/api/v1/reports/{v2.id}"
        assert v2.version == 2 and v2.status == "draft"
        # V1 审批不能自动批准 V2
        assert (await client.post(f"{v2_url}/publish", headers=OWNER)).status_code == 409
        assert (await client.post(f"{v2_url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{v2_url}/publish", headers=OWNER)).status_code == 409
        # V2 必须重新审核
        assert (await client.post(f"{v2_url}/approve", headers=OWNER)).status_code == 200
        # 审批绑定内容：批准后内容被改动，发布被内容哈希校验拒绝
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                stored = await session.get(ReportVersion, v2.id)
                stored.report_content = "批准后被改动"
                await session.commit()
        finally:
            await engine.dispose()
        tampered = await client.post(f"{v2_url}/publish", headers=OWNER)
        assert tampered.status_code == 409 and tampered.json()["error"]["code"] == "report_content_changed"
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                stored = await session.get(ReportVersion, v2.id)
                stored.report_content = "V2 申报说明"
                await session.commit()
        finally:
            await engine.dispose()
        assert (await client.post(f"{v2_url}/publish", headers=OWNER)).status_code == 200

        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                # 审批记录绑定具体版本与内容哈希，V1 审批不会指向 V2
                actions = (await session.scalars(select(ReportReviewAction))).all()
                assert all(item.report_version == 1 and item.content_hash == v1.content_hash
                           for item in actions if item.report_id == v1.id)
                assert [item for item in actions if item.report_id == v2.id] and all(
                    item.report_version == 2 and item.content_hash == v2.content_hash
                    for item in actions if item.report_id == v2.id)
                # V1 历史记录继续保留
                reports = (await session.scalars(select(ReportVersion).order_by(ReportVersion.version))).all()
                assert [item.version for item in reports] == [1, 2]
                stored_v1 = await session.get(ReportVersion, v1.id)
                assert stored_v1.status == "superseded" and stored_v1.content_hash == v1.content_hash
                audit = (await session.scalars(select(AuditLog).where(AuditLog.order_id == order_id))).all()
                assert {"report.created", "report.approved", "report.published"} <= {item.action for item in audit}
        finally:
            await engine.dispose()

        # V2 发布后不能被普通更新覆盖
        assert (await client.post(f"{v2_url}/submit-review", headers=OWNER)).status_code == 409
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                stored = await session.get(ReportVersion, v2.id)
                stored.report_content = "发布后被普通更新覆盖"
                await session.commit()
        finally:
            await engine.dispose()
        overwrite = await client.post(f"{v2_url}/publish", headers=OWNER)
        assert overwrite.status_code == 409 and overwrite.json()["error"]["code"] == "invalid_report_transition"
        # 客户只能取得已发布版本
        visible = (await client.get(f"/api/v1/orders/{order_id}/reports", headers=ALICE)).json()
        assert [item["id"] for item in visible] == [v2.id]

    exercise(tmp_path, monkeypatch, scenario)


def test_classification_change_invalidates_approved_report(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        _, ticket, _ = await make_batch_with_exception(client, order_id)
        v1 = await create_report(client, order_id, 1, "分类变化前 V1")
        url = f"/api/v1/reports/{v1.id}"
        assert (await client.post(f"{url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{url}/approve", headers=OWNER)).status_code == 200

        # 账务分类变化使已批准成果失效
        corrected = await client.post(f"/api/v1/exceptions/{ticket['id']}/decisions", json={
            "decision": "correct_classification", "reason": "确认为客户退款",
            "target_version": 1, "classification_after": "customer_refund"}, headers=OWNER)
        assert corrected.status_code == 201, corrected.text
        stale = await client.post(f"{url}/publish", headers=OWNER)
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_report"

        # 恢复路径：基于当前数据生成 V2 并重新审核
        v2 = await create_report(client, order_id, 2, "分类更正后 V2")
        v2_url = f"/api/v1/reports/{v2.id}"
        assert (await client.post(f"{v2_url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{v2_url}/approve", headers=OWNER)).status_code == 200
        assert (await client.post(f"{v2_url}/publish", headers=OWNER)).status_code == 200
        assert v2.exception_snapshot[0]["business_classification"] == "customer_refund"

    exercise(tmp_path, monkeypatch, scenario)


def test_evidence_change_invalidates_pending_and_approved_results(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        _, ticket, _ = await make_batch_with_exception(client, order_id)
        v1 = await create_report(client, order_id, 1, "证据变化前 V1")
        url = f"/api/v1/reports/{v1.id}"
        assert (await client.post(f"{url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{url}/approve", headers=OWNER)).status_code == 200

        # 证据材料变化：客户补充材料后已批准成果不能发布
        supplement = await client.post(f"/api/v1/exceptions/{ticket['id']}/supplements",
                                       data={"explanation": "补充付款说明"}, headers=ALICE)
        assert supplement.status_code == 201, supplement.text
        stale = await client.post(f"{url}/publish", headers=OWNER)
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_report"

        # 证据材料在任务创建后变化：旧任务成果不能生成草稿
        batch, tickets, matches = await fetch_context(client, order_id)
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                task = await agent_service.create_task(
                    session, report_task_payload(order_id, batch, tickets, matches, 2,
                                                 idempotency_key="be2-10-12-report-v2-stale"))
                await agent_service.start_task(session, task.id)
                task_id = task.id
            late = await client.post(f"/api/v1/exceptions/{ticket['id']}/supplements",
                                     data={"explanation": "再次补充凭证"}, headers=ALICE)
            assert late.status_code == 201, late.text
            async with sessions() as session:
                await agent_service.complete_task(
                    session, task_id, report_output(order_id, 2, "过期输入的 V2"))
                with pytest.raises(AppError) as error:
                    await report_service.create_from_agent_task(session, task_id)
                assert error.value.code == "stale_report_source"
        finally:
            await engine.dispose()

        # 恢复路径：任务基于当前证据重建后可重新审核交付
        v2 = await create_report(client, order_id, 2, "证据更新后 V2")
        v2_url = f"/api/v1/reports/{v2.id}"
        assert (await client.post(f"{v2_url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{v2_url}/approve", headers=OWNER)).status_code == 200
        assert (await client.post(f"{v2_url}/publish", headers=OWNER)).status_code == 200

    exercise(tmp_path, monkeypatch, scenario)


# ---------------------------------------------------------------- 工作流恢复


def test_recovery_lifecycle_restart_repeated_recovery_and_failing_again(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                task = await agent_service.create_task(session, reception_task(order_id, "be2-10-12-recovery"))
                task_id, run_id = task.id, task.run_id
                # 1. 正常运行
                assert (await agent_service.start_task(session, task_id)).status == "running"
                # 2. 中途暂停（保存检查点）
                await agent_service.save_checkpoint(session, run_id, {"cursor": 2, "stage": "waiting_material"})
                assert (await agent_service.pause_task(session, task_id)).status == "paused"
        finally:
            await engine.dispose()

        # 6/7. 服务异常退出后重启：全新连接下状态与检查点持久化
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                saved_task = await session.get(AgentTask, task_id)
                saved_run = await session.get(AgentRun, run_id)
                assert saved_task.status == "paused"
                assert saved_run.checkpoint_data == {"cursor": 2, "stage": "waiting_material"}
                # 8. 从检查点恢复
                resumed = await agent_service.resume_task(session, task_id)
                assert resumed.status == "running" and resumed.attempt_count == 2
                # 9. 重复恢复请求：拒绝且不产生重复副作用
                with pytest.raises(AppError) as repeated:
                    await agent_service.resume_task(session, task_id)
                assert repeated.value.code == "invalid_task_transition"
                assert (await session.get(AgentTask, task_id)).attempt_count == 2
                # 10. 恢复后继续执行
                completed = await agent_service.complete_task(session, task_id, reception_output())
                assert completed.status == "succeeded"
                # 已完成阶段不再执行副作用（重复投递不重复调用）
                gateway = FakeAgentGateway({"customer_reception": FakeResult("succeeded", reception_output())})
                redelivered = await agent_service.invoke_task(session, task_id, gateway)
                assert redelivered.status == "succeeded" and gateway.requests == []

                # 11. 恢复后再次失败
                second = await agent_service.create_task(session, reception_task(order_id, "be2-10-12-refail"))
                await agent_service.start_task(session, second.id)
                await agent_service.save_checkpoint(session, second.run_id, {"cursor": 5, "stage": "waiting"})
                await agent_service.pause_task(session, second.id)
                await agent_service.resume_task(session, second.id)
                failed = await agent_service.fail_task(session, second.id, "recovered but failed again")
                assert failed.status == "failed" and failed.attempt_count == 2
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_recovery_then_resume_finishes_delivery(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        await make_batch_with_exception(client, order_id)
        batch, tickets, matches = await fetch_context(client, order_id)

        # 生成草稿任务中途暂停（服务中断前保存检查点）
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                task = await agent_service.create_task(
                    session, report_task_payload(order_id, batch, tickets, matches, 1))
                task_id, run_id = task.id, task.run_id
                await agent_service.start_task(session, task.id)
                await agent_service.save_checkpoint(session, run_id, {"stage": "drafting"})
                assert (await agent_service.pause_task(session, task.id)).status == "paused"
        finally:
            await engine.dispose()

        # 服务重启后从检查点恢复并完成任务
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                await agent_service.resume_task(session, task_id)
                await agent_service.complete_task(
                    session, task_id, report_output(order_id, 1, "恢复后完成的 V1"))
                report = await report_service.create_from_agent_task(session, task_id)
        finally:
            await engine.dispose()

        # 等待人工审批：订单进入待审状态并跨重启保留
        url = f"/api/v1/reports/{report.id}"
        assert (await client.post(f"{url}/submit-review", headers=OWNER)).status_code == 200
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                order = await session.get(Order, order_id)
                assert order.status == "awaiting_owner_review"
        finally:
            await engine.dispose()

        # 恢复后完成交付
        assert (await client.post(f"{url}/approve", headers=OWNER)).status_code == 200
        assert (await client.post(f"{url}/publish", headers=OWNER)).status_code == 200
        assert (await client.get(url, headers=ALICE)).status_code == 200

    exercise(tmp_path, monkeypatch, scenario)


def test_waiting_states_and_blocked_status_cannot_be_bypassed(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        upload = await client.post(
            f"/api/v1/orders/{order_id}/files", data={"file_category": "invoice_image"},
            files=[("files", ("invoice.png", png_bytes(), "image/png"))], headers=ALICE)
        assert upload.status_code == 201, upload.text
        file_id = upload.json()["files"][0]["id"]

        # 等待材料补充：审核要求补传后订单停在 awaiting_customer
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                task = await agent_service.create_task(session, AgentTaskCreate(
                    order_id=order_id, agent_role="material_review", task_type="material_review",
                    idempotency_key="be2-10-12-material", correlation_id="be2-10-12-material",
                    input_payload={"order_id": order_id, "file_id": file_id,
                                   "file_category": "invoice_image", "mime_type": "image/png"}))
                await agent_service.start_task(session, task.id)
                await agent_service.complete_task(session, task.id, {
                    "file_id": file_id, "review_status": "NEEDS_REUPLOAD", "is_invoice": True,
                    "confidence": 0.40})
                order = await session.get(Order, order_id)
                assert order.status == "awaiting_customer"
                # 阻塞状态不能绕过：awaiting_customer 不得直接交付
                with pytest.raises(AppError) as blocked:
                    await order_state.move(session, order_id, "delivered", "bypass", "system", None)
                assert blocked.value.code == "invalid_order_transition"
        finally:
            await engine.dispose()

        await make_batch_with_exception(client, order_id)

        # 等待人工审批：待审状态不能被越权或未审批绕过
        report = await create_report(client, order_id, 1, "等待审批的 V1")
        url = f"/api/v1/reports/{report.id}"
        assert (await client.post(f"{url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{url}/approve", headers=ALICE)).status_code == 403
        assert (await client.post(f"{url}/publish", headers=OWNER)).status_code == 409

        # 阻塞状态不能绕过：未解决异常披露被抹掉后不得通过审批
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                stored = await session.get(ReportVersion, report.id)
                stored.unresolved_items = []
                stored.content_hash = report_service._content_hash(stored)
                await session.commit()
        finally:
            await engine.dispose()
        forged = await client.post(f"{url}/approve", headers=OWNER)
        assert forged.status_code == 409
        assert forged.json()["error"]["code"] == "unresolved_exception_undisclosed"

    exercise(tmp_path, monkeypatch, scenario)


# ---------------------------------------------------------------- 幂等


def test_repeated_submissions_consumption_and_publish_stay_idempotent(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        await make_batch_with_exception(client, order_id)
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                # 相同请求重复提交不会重复创建任务
                data = reception_task(order_id, "be2-10-12-idem")
                task = await agent_service.create_task(session, data)
                again = await agent_service.create_task(session, data)
                assert again.id == task.id
                rows = (await session.scalars(select(AgentTask).where(
                    AgentTask.idempotency_key == "be2-10-12-idem"))).all()
                assert len(rows) == 1
                queued = (await session.scalars(select(WorkflowEvent).where(
                    WorkflowEvent.event_type == "agent.task.queued",
                    WorkflowEvent.task_id == task.id))).all()
                assert len(queued) == 1
                with pytest.raises(AppError) as conflict:
                    await agent_service.create_task(session, data.model_copy(update={"input_payload": {
                        "order_id": order_id, "customer_message": "不同的请求", "submitted_file_ids": []}}))
                assert conflict.value.code == "idempotency_conflict"
        finally:
            await engine.dispose()

        # 成功的成果生成不会重复产生不一致记录
        report = await create_report(client, order_id, 1, "幂等验证 V1")
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                duplicate = await report_service.create_from_agent_task(session, report.source_task_id)
                assert duplicate.id == report.id
                stored = (await session.scalars(select(ReportVersion))).all()
                assert len(stored) == 1 and stored[0].content_hash == report.content_hash
        finally:
            await engine.dispose()

        # 成功的资料包生成不会重复发布（二次发布被拒绝且不改写结果）
        url = f"/api/v1/reports/{report.id}"
        assert (await client.post(f"{url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{url}/approve", headers=OWNER)).status_code == 200
        first = await client.post(f"{url}/publish", headers=OWNER)
        assert first.status_code == 200
        published_at = first.json()["published_at"]
        assert (await client.post(f"{url}/publish", headers=OWNER)).status_code == 409
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                audits = (await session.scalars(select(AuditLog).where(
                    AuditLog.action == "report.published"))).all()
                assert len(audits) == 1
                stored = await session.get(ReportVersion, report.id)
                assert stored.published_at is not None and stored.status == "published"
        finally:
            await engine.dispose()
        assert (await client.get(url, headers=OWNER)).json()["published_at"] == published_at

        # 相同事件不会重复消费：游标推进后不重复返回，重复读取不产生新事件
        stream = await client.get(f"/api/v1/orders/{order_id}/events/stream?follow=false", headers=ALICE)
        frames = [part for part in stream.text.split("\n\n") if part]
        ids = [int(frame.splitlines()[0].removeprefix("id: ")) for frame in frames]
        tail = await client.get(
            f"/api/v1/orders/{order_id}/events/stream?follow=false&after_id={ids[-1]}", headers=ALICE)
        assert tail.text == ""
        repeat = await client.get(
            f"/api/v1/orders/{order_id}/events/stream?follow=false&after_id={ids[0] - 1}", headers=ALICE)
        repeat_ids = [int(part.splitlines()[0].removeprefix("id: "))
                      for part in repeat.text.split("\n\n") if part]
        assert repeat_ids == ids

        # 重试不会破坏原有审批记录
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                before = [(item.action, item.report_version, item.content_hash)
                          for item in (await session.scalars(select(ReportReviewAction))).all()]
                retry_task = await agent_service.create_task(session, reception_task(order_id, "be2-10-12-retry"))
                await agent_service.start_task(session, retry_task.id)
                failed = await agent_service.fail_task(session, retry_task.id, "first attempt failed")
                assert failed.status == "failed"
                after = [(item.action, item.report_version, item.content_hash)
                         for item in (await session.scalars(select(ReportReviewAction))).all()]
                assert after == before
                assert len(after) == 1 and after[0][0] == "approved"
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


# ---------------------------------------------------------------- 权限


def test_permission_boundaries_and_version_specific_approval(tmp_path, monkeypatch):
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        await make_batch_with_exception(client, order_id)
        report = await create_report(client, order_id, 1, "权限验证 V1")
        url = f"/api/v1/reports/{report.id}"

        # 客户不能越权审批
        assert (await client.post(f"{url}/submit-review", headers=ALICE)).status_code == 403
        assert (await client.post(f"{url}/approve", headers=ALICE)).status_code == 403
        assert (await client.post(f"{url}/publish", headers=ALICE)).status_code == 403
        # 无权限用户不能发布（全局动作 403；跨租户读取 404）
        assert (await client.get(url, headers=BOB)).status_code == 404
        assert (await client.post(f"{url}/publish", headers=BOB)).status_code == 403

        # Agent 不能批准自己的成果：产出仍是草稿且无审批记录
        assert report.status == "draft"
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                actions = (await session.scalars(select(ReportReviewAction))).all()
                assert actions == []
                with pytest.raises(AppError) as denied:
                    await report_service.approve(
                        session, report.id, Principal(user_id="risk_delivery", role="customer"))
                assert denied.value.code == "forbidden"
        finally:
            await engine.dispose()

        # 审批绑定具体草稿版本与内容哈希
        assert (await client.post(f"{url}/submit-review", headers=OWNER)).status_code == 200
        assert (await client.post(f"{url}/approve", headers=OWNER)).status_code == 200
        engine, sessions = _sessions()
        try:
            async with sessions() as session:
                approval = (await session.scalars(select(ReportReviewAction))).one()
                approval.content_hash = "0" * 64
                await session.commit()
        finally:
            await engine.dispose()
        unbound = await client.post(f"{url}/publish", headers=OWNER)
        assert unbound.status_code == 409 and unbound.json()["error"]["code"] == "approval_missing"

    exercise(tmp_path, monkeypatch, scenario)


# ---------------------------------------------------------------- Agent 工作流检查点（只读验证）


async def test_agent_workflow_repeated_recovery_keeps_review_idempotent(tmp_path):
    from agents.support import ScriptedRunner

    from app.agents.checkpoints import create_checkpoint_storage
    from app.agents.contracts import OrderInput, RunIdentity
    from app.agents.demo import FixtureBackend
    from app.agents.errors import AgentError
    from app.agents.fixtures import create_fixtures
    from app.agents.workflow import build_workflow

    fixtures = tmp_path / "synthetic"
    create_fixtures(fixtures)
    backend = FixtureBackend(tmp_path / "runtime", fixtures)
    order = OrderInput.model_validate_json((fixtures / "order.json").read_text(encoding="utf-8"))
    backend.put_order(order)
    identity = RunIdentity(order_id="demo-order", run_id="demo-run", revision=1)

    class FailInvoice(ScriptedRunner):
        async def generate(self, role, prompt, schema, budget, **kwargs):
            if role == "invoice":
                await budget.reserve()
                raise AgentError("simulated transport failure")
            return await super().generate(role, prompt, schema, budget, **kwargs)

    storage = create_checkpoint_storage(tmp_path / "checkpoints")
    workflow = build_workflow(backend, storage, "be2-10-12", runner=FailInvoice(fixtures), max_requests=64)
    with pytest.raises(AgentError):
        await workflow.run(identity)
    checkpoint = await storage.get_latest(workflow_name="be2-10-12")
    assert checkpoint is not None

    # 第一次恢复：从检查点继续到人工待办
    workflow = build_workflow(backend, storage, "be2-10-12", runner=ScriptedRunner(fixtures), max_requests=64)
    first = await workflow.run(checkpoint_id=checkpoint.checkpoint_id)
    request = first.get_request_info_events()[0].data

    # 重复恢复请求：同一检查点再次恢复仍落到同一待办，不产生新的审批待办
    workflow = build_workflow(backend, storage, "be2-10-12", runner=ScriptedRunner(fixtures), max_requests=64)
    second = await workflow.run(checkpoint_id=checkpoint.checkpoint_id)
    repeated_request = second.get_request_info_events()[0].data
    assert repeated_request.request_id == request.request_id
    latest = await backend.load_artifact(identity, "review")
    assert latest["request_id"] == request.request_id
    assert await backend.load_artifact(identity, "approval") is None
