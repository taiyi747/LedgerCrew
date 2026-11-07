import asyncio
import csv
import json
from pathlib import Path
from uuid import uuid4

from live_support import LiveScriptedRunner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_stage2 import exercise

from app.db.session import make_engine
from app.live import service
from app.live.models import Delegation, WorkflowRun
from app.live.worker import execute_run
from app.models import WorkflowEvent


async def run_worker(tmp_path, runner, kind="processing"):
    engine = make_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            token = str(uuid4())
            run_id = await service.claim_run(session, kind, token)
        if run_id:
            await execute_run(
                sessions, run_id, token, runner=runner, data_dir=tmp_path / "checkpoints", raise_errors=True
            )
        return run_id
    finally:
        await engine.dispose()


async def create_live_order(client):
    headers = {"X-User-Id": "alice"}
    studio = await client.post(
        "/api/v1/studios",
        json={"name": "松石设计工作室", "business_type": "digital_services"},
        headers=headers,
    )
    assert studio.status_code == 201, studio.text
    response = await client.post(
        "/api/v1/orders",
        json={
            "studio_id": studio.json()["id"],
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
            "service_scope": "monthly_records",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json(), headers


def test_delegation_todos_are_planned_tracked_and_traced(tmp_path, monkeypatch):
    async def scenario(client, storage):
        order_id, _customer, _created_run = await prepare_live_order(client)
        runner = LiveScriptedRunner()
        await run_worker(tmp_path, runner)
        owner = {"X-User-Id": "owner"}
        trace = (
            await client.get(
                f"/api/v1/owner/agents/invoice_processing/trace?order_id={order_id}", headers=owner
            )
        ).json()
        delegations = [d for d in trace["delegations"] if d["task_type"] == "invoice_batch"]
        assert delegations, trace
        todos = delegations[0]["todos"]
        assert todos, delegations[0]
        assert all(t["title"] and t["status"] == "completed" for t in todos), todos
        assert [t["id"] for t in todos] == [f"t{i + 1}" for i in range(len(todos))]
        dashboard = (await client.get("/api/v1/owner/dashboard", headers=owner)).json()
        agent = next(a for a in dashboard["agents"] if a["id"] == "invoice_processing")
        assert agent["todos"] == {"done": len(todos), "total": len(todos)}, agent
        engine = make_engine()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                rows = (
                    await session.scalars(
                        select(WorkflowEvent).where(WorkflowEvent.event_type == "delegation.todos")
                    )
                ).all()
        finally:
            await engine.dispose()
        assert rows, "规划与进度更新应发出 delegation.todos 事件"

    exercise(tmp_path, monkeypatch, scenario)


def test_work_tools_refuse_before_the_agent_plans(tmp_path, monkeypatch):
    async def scenario(client, storage):
        _order_id, _customer, _created_run = await prepare_live_order(client)
        refusals = []

        class GuardProbe(LiveScriptedRunner):
            async def generate(self, role, prompt, schema, budget, *, tools=None, image=None):
                named = {tool.__name__: tool for tool in tools or []}
                if "save_customer_message" in named:
                    refusals.append(json.loads(await named["save_customer_message"]("先不规划直接干。")))
                return await super().generate(role, prompt, schema, budget, tools=tools, image=image)

        await run_worker(tmp_path, GuardProbe())
        assert refusals, "业务工具应先拒绝未规划的调用"
        assert "plan_todos" in refusals[0]["error"], refusals

    exercise(tmp_path, monkeypatch, scenario)


def test_run_budget_covers_large_material_batches(tmp_path, monkeypatch):
    async def scenario(client, storage):
        order_id, customer, created = await prepare_live_order(client)
        # 6 张票据图片 + 1 份流水 CSV：运行预算统一 300 次模型请求。
        assert created["request_limit"] == 300, created
        state = (await client.get(f"/api/v1/orders/{order_id}/runs/current", headers=customer)).json()
        assert state["request_limit"] == created["request_limit"], state

    exercise(tmp_path, monkeypatch, scenario)


def test_dispatch_runs_batched_delegations_in_parallel(tmp_path, monkeypatch):
    async def scenario(client, storage):
        _order_id, _customer, _created_run = await prepare_live_order(client)
        state = {"active": 0, "peak": 0}

        class ParallelProbe(LiveScriptedRunner):
            async def generate(self, role, prompt, schema, budget, *, tools=None, image=None):
                from app.live.contracts import TASK_ROLE, Assignment, SupervisorDecision

                if schema is SupervisorDecision:
                    named = {tool.__name__: tool for tool in tools or []}
                    snapshot = json.loads(prompt.split("\n")[-1])
                    eligible = snapshot["eligible_tasks"]
                    if len(eligible) >= 2:
                        # 同批派出两件独立任务，验证 Dispatch 并发执行。
                        await named["delegate_tasks"](
                            [
                                Assignment(
                                    agent_role=TASK_ROLE[task], task_type=task, goal="同批派出的独立任务"
                                ).model_dump()
                                for task in eligible[:2]
                            ]
                        )
                        return SupervisorDecision(action="delegated", summary="同批派出两件独立任务")
                if schema.__name__ == "RoleResult":
                    state["active"] += 1
                    state["peak"] = max(state["peak"], state["active"])
                    await asyncio.sleep(0.05)
                    try:
                        return await super().generate(role, prompt, schema, budget, tools=tools, image=image)
                    finally:
                        state["active"] -= 1
                return await super().generate(role, prompt, schema, budget, tools=tools, image=image)

        await run_worker(tmp_path, ParallelProbe())
        assert state["peak"] >= 2, f"同批派单应并发执行，实际并发峰值 {state['peak']}"

    exercise(tmp_path, monkeypatch, scenario)


def test_owner_facing_notes_reject_machine_text():
    import pytest

    from app.live.engine import owner_note

    assert owner_note("重复发票一件、缺失发票若干，请决定是否接受未解决。")
    for bad in (
        "EX-E014E125933946EB8FD65814020F2651 需要决定",
        "批次 cc6371fb-aee1-4460-ab04-b2cde7f9e595 存在异常",
        "eligible_tasks 为空，无法继续派发",
    ):
        with pytest.raises(ValueError):
            owner_note(bad)


def test_supervised_live_flow_and_report_delivery(tmp_path, monkeypatch):
    async def scenario(client, storage):
        order_id, customer, _created_run = await prepare_live_order(client)
        runner = LiveScriptedRunner()
        await run_worker(tmp_path, runner)
        state = (await client.get(f"/api/v1/orders/{order_id}/runs/current", headers=customer)).json()
        assert state["status"] == "paused", state
        tickets = (await client.get(f"/api/v1/orders/{order_id}/exceptions", headers=customer)).json()
        assert len(tickets) == 3, tickets
        assert [t["difference_cents"] for t in tickets if t["exception_type"] == "AMOUNT_MISMATCH"] == [27000]
        owner = {"X-User-Id": "owner"}
        for ticket in tickets:
            decision = await client.post(
                f"/api/v1/exceptions/{ticket['id']}/decisions",
                headers=owner,
                json={"decision": "accept_unresolved", "reason": "保留未核实事项", "target_version": 1},
            )
            assert decision.status_code == 201, decision.text
        import pytest

        from app.agents.errors import AgentError

        class InterruptedResume(LiveScriptedRunner):
            async def generate(self, *args, **kwargs):
                raise AgentError("模拟恢复后的模型暂时不可用")

        with pytest.raises(AgentError):
            await run_worker(tmp_path, InterruptedResume())
        failed = (await client.get(f"/api/v1/orders/{order_id}/runs/current", headers=customer)).json()
        assert failed["status"] == "failed"
        assert (await client.post(f"/api/v1/runs/{failed['id']}/retry", headers=customer)).status_code == 202
        await run_worker(tmp_path, runner)
        reports = await client.get(f"/api/v1/orders/{order_id}/reports", headers=owner)
        assert len(reports.json()) == 1, reports.text
        report = reports.json()[0]
        assert (await client.get(f"/api/v1/reports/{report['id']}", headers=customer)).status_code == 404
        # Rejected content must produce a new version and a new approval.
        old_id = report["id"]
        assert (
            await client.post(f"/api/v1/reports/{old_id}/submit-review", headers=owner)
        ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/reports/{old_id}/reject",
                headers=owner,
                json={"reason": "请改写异常说明，保留原始金额"},
            )
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/reports/{old_id}/submit-review", headers=owner)
        ).status_code == 409
        await run_worker(tmp_path, runner)
        reports = (await client.get(f"/api/v1/orders/{order_id}/reports", headers=owner)).json()
        report = max(reports, key=lambda r: r["version"])
        assert report["version"] == 2
        assert (await client.post(f"/api/v1/reports/{old_id}/approve", headers=owner)).status_code == 409
        for action in ("submit-review", "approve", "publish"):
            r = await client.post(
                f"/api/v1/reports/{report['id']}/{action}", headers=owner, json={"reason": "已核验本版本"}
            )
            assert r.status_code == 200, r.text
        await run_worker(tmp_path, runner)
        assert (await client.get(f"/api/v1/orders/{order_id}/runs/current", headers=customer)).json()[
            "status"
        ] == "succeeded"
        assert (
            await client.get(f"/api/v1/reports/{report['id']}/download", headers=customer)
        ).status_code == 200
        engine = make_engine()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as s:
            ds = list((await s.scalars(select(Delegation).where(Delegation.order_id == order_id))).all())
            assert ds and all(d.decision_id and d.status == "succeeded" and d.receipts for d in ds)
        await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


async def prepare_live_order(client):
    order, customer = await create_live_order(client)
    order_id = order["id"]
    root = Path(__file__).resolve().parents[2] / "fixtures/mvp"
    for i in range(1, 7):
        response = await client.post(
            f"/api/v1/orders/{order_id}/files",
            headers=customer,
            data={"file_category": "invoice_image"},
            files={"files": (f"receipt-{i}.png", (root / f"receipt-{i:02}.png").read_bytes(), "image/png")},
        )
        assert response.status_code == 201, response.text
    data = "transaction_date,counterparty,direction,amount,description,external_id\n"
    for row in csv.DictReader((root / "statement.csv").read_text(encoding="utf-8-sig").splitlines()):
        data += f"{row['date']},{row['counterparty']},OUT,{row['amount']},测试,{row['transaction_id']}\n"
    file = await client.post(
        f"/api/v1/orders/{order_id}/files",
        headers=customer,
        data={"file_category": "bank_statement_csv"},
        files={"files": ("statement.csv", data.encode(), "text/csv")},
    )
    imported = await client.post(
        f"/api/v1/orders/{order_id}/imports/csv",
        headers=customer,
        json={"file_id": file.json()["files"][0]["id"]},
    )
    assert imported.status_code == 201
    current = (await client.get(f"/api/v1/orders/{order_id}", headers=customer)).json()
    response = await client.post(
        f"/api/v1/orders/{order_id}/runs",
        headers=customer,
        json={"idempotency_key": "start-one", "expected_revision": current["input_revision"]},
    )
    assert response.status_code == 202, response.text
    return order_id, customer, response.json()


def test_delegation_guards_and_durable_budget(tmp_path, monkeypatch):
    async def scenario(client, _):
        from datetime import timedelta

        import pytest

        from app.agents.contracts import RunIdentity
        from app.agents.errors import AgentError, RequestBudgetExceeded
        from app.agents.runner import RequestBudget
        from app.core.exceptions import AppError
        from app.db.types import utc_now
        from app.live.contracts import Assignment
        from app.live.engine import LiveRuntime
        from app.live.gateway import BudgetStore

        order_id, customer, run = await prepare_live_order(client)
        assert (await client.get("/api/v1/owner/dashboard", headers=customer)).status_code == 403
        assert (
            await client.get(f"/api/v1/orders/{order_id}/runs/current", headers={"X-User-Id": "bob"})
        ).status_code == 404
        same = await client.post(
            f"/api/v1/orders/{order_id}/runs",
            headers=customer,
            json={"idempotency_key": "another-click", "expected_revision": run["input_revision"]},
        )
        assert same.json()["id"] == run["id"]
        stale = await client.post(
            f"/api/v1/orders/{order_id}/runs",
            headers=customer,
            json={"idempotency_key": "stale", "expected_revision": 1},
        )
        assert stale.status_code == 409
        root = Path(__file__).resolve().parents[2] / "fixtures/mvp"
        upload = await client.post(
            f"/api/v1/orders/{order_id}/files",
            headers=customer,
            data={"file_category": "invoice_image"},
            files={"files": ("new.png", (root / "receipt-01.png").read_bytes(), "image/png")},
        )
        assert upload.status_code == 409
        engine = make_engine()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as s:
                token = str(uuid4())
                await service.claim_run(s, "processing", token)
                db_run = await s.get(WorkflowRun, run["id"])
                for assignment, revision in [
                    (
                        Assignment(
                            agent_role="data_reconciliation", task_type="reconcile_order", goal="too soon"
                        ),
                        run["input_revision"],
                    ),
                    (
                        Assignment(
                            agent_role="invoice_processing", task_type="invoice_batch", goal="old version"
                        ),
                        1,
                    ),
                    (
                        Assignment(
                            agent_role="invoice_processing",
                            task_type="invoice_batch",
                            goal="cross order",
                            input_refs=["other-order-file"],
                        ),
                        run["input_revision"],
                    ),
                ]:
                    with pytest.raises(AppError):
                        await service.delegate(s, db_run, "decision", assignment, revision)
                db_run.request_limit = 2
                await s.commit()
            store = BudgetStore(sessions, run["id"], token)
            identity = RunIdentity(order_id=order_id, run_id=run["id"], revision=run["input_revision"])
            await RequestBudget(store, identity, 2).reserve()
            # A recreated gateway reads the persisted count, including concurrent reservations.
            budget = RequestBudget(store, identity, 2)
            await budget.reserve()
            with pytest.raises(RequestBudgetExceeded):
                await budget.reserve()
            async with sessions() as s:
                db_run = await s.get(WorkflowRun, run["id"])
                assert db_run.requests_used == 2
                db_run.lease_expires_at = utc_now() - timedelta(seconds=1)
                await s.commit()
            with pytest.raises(AgentError):
                await store.load_artifact(identity, "usage")
            async with sessions() as s:
                replacement = str(uuid4())
                assert await service.claim_run(s, "processing", replacement) == run["id"]
            with pytest.raises(AgentError):
                await store.load_artifact(identity, "usage")

            # A model claiming it delegated without actually using a tool must fail.
            class Liar:
                async def generate(self, role, prompt, schema, budget, **kw):
                    from app.live.contracts import SupervisorDecision

                    return SupervisorDecision(action="delegated", summary="only a claim")

            runtime = LiveRuntime(sessions, run["id"], replacement, runner=Liar())
            with pytest.raises(AgentError, match="工具回执"):
                await runtime.coordinate()
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_customer_supplement_and_chat_are_separate(tmp_path, monkeypatch):
    async def scenario(client, _):
        order_id, customer, run = await prepare_live_order(client)
        runner = LiveScriptedRunner()
        await run_worker(tmp_path, runner)
        before = (await client.get(f"/api/v1/orders/{order_id}/reconciliation", headers=customer)).json()
        tickets = (await client.get(f"/api/v1/orders/{order_id}/exceptions", headers=customer)).json()
        mismatch = next(t for t in tickets if t["exception_type"] == "AMOUNT_MISMATCH")
        owner = {"X-User-Id": "owner"}
        question = {"client_message_id": "one-question", "content": "差额能直接核销吗？"}
        one = await client.post(f"/api/v1/orders/{order_id}/messages", headers=customer, json=question)
        two = await client.post(f"/api/v1/orders/{order_id}/messages", headers=customer, json=question)
        assert one.json() == two.json()
        await run_worker(tmp_path, runner, kind="chat")
        assert (
            await client.get(f"/api/v1/orders/{order_id}/reconciliation", headers=customer)
        ).json() == before
        messages = (await client.get(f"/api/v1/orders/{order_id}/messages", headers=customer)).json()
        assert any(
            m["role"] == "assistant" and m["workflow_run_id"] == one.json()["workflow_run_id"]
            for m in messages
        )
        decision = await client.post(
            f"/api/v1/exceptions/{mismatch['id']}/decisions",
            headers=owner,
            json={"decision": "request_supplement", "reason": "请补充运费依据", "target_version": 1},
        )
        assert decision.status_code == 201, decision.text
        await run_worker(tmp_path, runner)
        state = (await client.get(f"/api/v1/orders/{order_id}/runs/current", headers=customer)).json()
        assert state["wait_reason"] == "waiting_customer"
        assert state["checkpoint_id"] if "checkpoint_id" in state else state["status"] == "paused"
        supplement = await client.post(
            f"/api/v1/exceptions/{mismatch['id']}/supplements",
            headers=customer,
            data={"explanation": "可能是运费，没有凭证，不改变原始金额。"},
        )
        assert supplement.status_code == 201, supplement.text
        await run_worker(tmp_path, runner)
        after = (await client.get(f"/api/v1/orders/{order_id}/reconciliation", headers=customer)).json()
        assert after["id"] == before["id"]
        updated = (await client.get(f"/api/v1/orders/{order_id}/exceptions", headers=customer)).json()
        assert next(t for t in updated if t["id"] == mismatch["id"])["difference_cents"] == 27000
        engine = make_engine()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as s:
                state = await service.snapshot(s, run["id"])
                assert state["customer_supplements"][0]["explanation"].startswith("可能是运费")
                assert state["owner_decisions"][0]["decision"] == "request_supplement"
                live = await s.get(WorkflowRun, run["id"])
                assert live.checkpoint_id and live.pending_request_id and live.requests_used > 0
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_specialist_requires_tool_receipt_and_versions(tmp_path, monkeypatch):
    async def scenario(client, _):
        import pytest

        from app.agents.errors import AgentError
        from app.live.contracts import Assignment, RoleResult
        from app.live.engine import LiveRuntime

        _order_id, _customer, run = await prepare_live_order(client)
        engine = make_engine()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                token = str(uuid4())
                await service.claim_run(session, "processing", token)
                live = await session.get(WorkflowRun, run["id"])
                task = await service.delegate(
                    session,
                    live,
                    "actual-supervisor-decision",
                    Assignment(
                        agent_role="invoice_processing", task_type="invoice_batch", goal="提取本单票据"
                    ),
                    run["input_revision"],
                )
                await session.commit()
                delegation_id = task.id

            class NoTools:
                async def generate(self, role, prompt, schema, budget, **kwargs):
                    await budget.reserve()
                    return RoleResult(summary="声称已经识别完成", evidence_refs=[])

            runtime = LiveRuntime(sessions, run["id"], token, runner=NoTools())
            with pytest.raises(AgentError, match="工具"):
                await runtime.execute(delegation_id)
            async with sessions() as session:
                task = await session.get(Delegation, delegation_id)
                assert task.status == "failed" and not task.receipts
                task.input_revision -= 1
                await session.commit()
            with pytest.raises(AgentError, match="版本"):
                await runtime.execute(delegation_id)
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)


def test_stale_upload_is_rejected_and_old_source_retained(tmp_path, monkeypatch):
    async def scenario(client, _):
        order, customer = await create_live_order(client)
        order_id = order["id"]
        root = Path(__file__).resolve().parents[2] / "fixtures/mvp"

        def file():
            return {"files": ("invoice.png", (root / "receipt-01.png").read_bytes(), "image/png")}

        original = await client.post(
            f"/api/v1/orders/{order_id}/files",
            headers=customer,
            data={"file_category": "invoice_image", "expected_revision": 1},
            files=file(),
        )
        old = original.json()["files"][0]
        stale = await client.post(
            f"/api/v1/orders/{order_id}/files",
            headers=customer,
            data={"file_category": "invoice_image", "expected_revision": 1},
            files=file(),
        )
        assert stale.status_code == 409
        replacement = await client.post(
            f"/api/v1/orders/{order_id}/files",
            headers=customer,
            data={"file_category": "invoice_image", "expected_revision": 2, "replaces_file_id": old["id"]},
            files=file(),
        )
        assert replacement.status_code == 201, replacement.text
        files = (await client.get(f"/api/v1/orders/{order_id}/files", headers=customer)).json()
        assert len(files) == 2 and sum(f["is_active"] for f in files) == 1
        assert (await client.get(f"/api/v1/files/{old['id']}/download", headers=customer)).status_code == 200

    exercise(tmp_path, monkeypatch, scenario)


def test_closing_failure_does_not_revoke_published_delivery(tmp_path, monkeypatch):
    async def scenario(client, _):
        import pytest

        from app.agents.errors import AgentError
        from app.models import Order

        order, _customer = await create_live_order(client)
        engine = make_engine()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                row = await session.get(Order, order["id"])
                row.status = "delivered"
                live = WorkflowRun(
                    order_id=order["id"],
                    kind="processing",
                    status="queued",
                    stage="supervisor",
                    input_revision=1,
                    idempotency_key="close-delivered",
                    created_by="alice",
                )
                session.add(live)
                await session.commit()
                token = str(uuid4())
                await service.claim_run(session, "processing", token)
                run_id = live.id

            class FailedModel:
                async def generate(self, *args, **kwargs):
                    raise AgentError("模拟模型超时")

            with pytest.raises(AgentError):
                await execute_run(
                    sessions,
                    run_id,
                    token,
                    runner=FailedModel(),
                    data_dir=tmp_path / "checkpoints",
                    raise_errors=True,
                )
            async with sessions() as session:
                assert (await session.get(WorkflowRun, run_id)).status == "failed"
                assert (await session.get(Order, order["id"])).status == "delivered"
        finally:
            await engine.dispose()

    exercise(tmp_path, monkeypatch, scenario)
