from __future__ import annotations

import asyncio

import pytest

from app.agents.checkpoints import create_checkpoint_storage
from app.agents.contracts import HumanReply, ReviewRequest, RunIdentity
from app.agents.errors import ModelOutputError, RequestBudgetExceeded, StaleReviewError
from app.agents.runner import RequestBudget
from app.agents.workflow import amount_to_minor, build_workflow, validate_reply

from .support import ScriptedRunner

IDENTITY = RunIdentity(order_id="demo-order", run_id="demo-run", revision=1)


def make_workflow(backend, fixture_dir, tmp_path, *, runner=None, max_requests=64):
    storage = create_checkpoint_storage(tmp_path / "checkpoints")
    runner = runner or ScriptedRunner(fixture_dir)
    return (
        build_workflow(backend, storage, "test-ledger", runner=runner, max_requests=max_requests),
        storage,
        runner,
    )


async def restart(backend, fixture_dir, tmp_path, request, action, comment="", report_version=None):
    workflow, storage, runner = make_workflow(backend, fixture_dir, tmp_path)
    checkpoint = await storage.get_latest(workflow_name="test-ledger")
    assert checkpoint
    reply = HumanReply(
        identity=request.identity,
        request_id=request.request_id,
        action=action,
        comment=comment,
        report_version=report_version,
    )
    result = await workflow.run(checkpoint_id=checkpoint.checkpoint_id, responses={request.request_id: reply})
    return result, runner


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2,580.00", 258000),
        ("￥ 36.90 元", 3690),
        ("0.01", 1),
        ("12.001", None),
        ("NaN", None),
        ("Infinity", None),
        ("-1", None),
        ("?", None),
        (None, None),
    ],
)
def test_money(raw, expected):
    assert amount_to_minor(raw) == expected


async def test_anomalies_restart_and_delivery(backend, fixture_dir, tmp_path):
    workflow, _, _ = make_workflow(backend, fixture_dir, tmp_path)
    result = await workflow.run(IDENTITY)
    request = result.get_request_info_events()[0].data
    assert request.kind == "exception"
    reconciliation = await backend.load_artifact(IDENTITY, "reconciliation:1")
    assert len(reconciliation["matches"]) == 4
    assert [i["difference_minor"] for i in reconciliation["issues"] if i["kind"] == "amount_mismatch"] == [
        27000
    ]
    assert sum(i["kind"] == "duplicate" for i in reconciliation["issues"]) == 1
    assert sum(i["kind"] == "missing_invoice" for i in reconciliation["issues"]) == 1
    assert reconciliation["invoice_total_minor"] == 403490
    before = (await backend.load_artifact(IDENTITY, "usage"))["requests"]
    result, second_runner = await restart(backend, fixture_dir, tmp_path, request, "keep_flagged")
    delivery = result.get_request_info_events()[0].data
    assert delivery.kind == "delivery"
    assert second_runner.calls == ["delivery"]
    assert (await backend.load_artifact(IDENTITY, "usage"))["requests"] == before + 1
    result, final_runner = await restart(
        backend, fixture_dir, tmp_path, delivery, "approve_delivery", report_version=delivery.report_version
    )
    outcome = result.get_outputs()[0]
    assert outcome.status == "delivery_approved"
    assert len(outcome.report.unresolved_issue_ids) == 3
    assert final_runner.calls == []


async def test_customer_info_remains_unverified(backend, fixture_dir, tmp_path):
    workflow, _, _ = make_workflow(backend, fixture_dir, tmp_path)
    result = await workflow.run(IDENTITY)
    request = result.get_request_info_events()[0].data
    result, _ = await restart(backend, fixture_dir, tmp_path, request, "request_info", "请补充差额说明")
    customer = result.get_request_info_events()[0].data
    assert customer.kind == "customer"
    order = await backend.load_order(IDENTITY.order_id)
    order.identity.revision = 2
    order.customer_notes.append("差额可能是运费，尚无凭证。")
    backend.put_order(order)
    result, runner = await restart(backend, fixture_dir, tmp_path, customer, "submit_information")
    new_request = result.get_request_info_events()[0].data
    assert new_request.identity.revision == 2
    assert new_request.kind == "exception"
    assert (
        "invoice" not in runner.calls
    )  # Immutable images reuse validated extraction, not changed conclusions.
    reconciliation = await backend.load_artifact(order.identity, "reconciliation:2")
    assert any(i["difference_minor"] == 27000 for i in reconciliation["issues"])


async def test_report_revision_rejects_old_approval(backend, fixture_dir, tmp_path):
    workflow, _, _ = make_workflow(backend, fixture_dir, tmp_path)
    first = (await workflow.run(IDENTITY)).get_request_info_events()[0].data
    result, _ = await restart(backend, fixture_dir, tmp_path, first, "keep_flagged")
    old = result.get_request_info_events()[0].data
    result, _ = await restart(
        backend,
        fixture_dir,
        tmp_path,
        old,
        "revise_report",
        "请明确列出未解决事项",
        report_version=old.report_version,
    )
    current = result.get_request_info_events()[0].data
    assert current.report_version == old.report_version + 1
    assert current.request_id != old.request_id
    with pytest.raises(StaleReviewError):
        validate_reply(
            current,
            HumanReply(
                identity=current.identity,
                request_id=old.request_id,
                action="approve_delivery",
                report_version=old.report_version,
            ),
        )


async def test_budget_persists_and_parallel_reservations(backend):
    budget = RequestBudget(backend, IDENTITY, 2)
    await asyncio.gather(budget.reserve(), budget.reserve())
    with pytest.raises(RequestBudgetExceeded):
        await RequestBudget(backend, IDENTITY, 2).reserve()
    assert (await backend.load_artifact(IDENTITY, "usage"))["requests"] == 2


async def test_normal_order_waits_for_delivery(backend, fixture_dir, tmp_path):
    order = await backend.load_order(IDENTITY.order_id)
    order.files = order.files[:4]
    order.transactions = order.transactions[:4]
    backend.put_order(order)
    workflow, _, runner = make_workflow(backend, fixture_dir, tmp_path)
    result = await workflow.run(IDENTITY)
    assert result.get_request_info_events()[0].data.kind == "delivery"
    assert "customer_service" not in runner.calls
    assert result.get_outputs() == []


async def test_unclear_invoice_requires_human(backend, fixture_dir, tmp_path):
    from app.agents.contracts import FileRef

    order = await backend.load_order(IDENTITY.order_id)
    order.files = [FileRef(id="unclear", name="unclear.png", mime_type="image/png")]
    backend.put_order(order)
    workflow, _, _ = make_workflow(backend, fixture_dir, tmp_path)
    result = await workflow.run(IDENTITY)
    assert result.get_request_info_events()[0].data.kind == "exception"
    invoices = await backend.load_artifact(IDENTITY, "invoices")
    assert invoices["items"][0]["amount_minor"] is None
    assert invoices["items"][0]["needs_review"] is True


async def test_wrong_reply_binding():
    request = ReviewRequest(
        identity=IDENTITY,
        request_id="review",
        kind="exception",
        question="核实",
        allowed_actions=["keep_flagged"],
        evidence_refs=[],
    )
    for identity, request_id, action in [
        (IDENTITY.model_copy(update={"revision": 2}), "review", "keep_flagged"),
        (IDENTITY, "wrong", "keep_flagged"),
        (IDENTITY, "review", "approve_delivery"),
    ]:
        with pytest.raises(StaleReviewError):
            validate_reply(request, HumanReply(identity=identity, request_id=request_id, action=action))


async def test_missing_tool_is_failure(backend, fixture_dir, tmp_path):
    from app.agents.contracts import ReconciliationAcknowledgement

    class NoTool(ScriptedRunner):
        async def generate(self, role, prompt, schema, budget, **kwargs):
            if role == "reconciliation":
                return ReconciliationAcknowledgement(summary="pretended completion")
            return await super().generate(role, prompt, schema, budget, **kwargs)

    workflow, _, _ = make_workflow(backend, fixture_dir, tmp_path, runner=NoTool(fixture_dir))
    with pytest.raises(ModelOutputError):
        await workflow.run(IDENTITY)
    assert any(e["type"] == "failed" for e in backend.events(IDENTITY))
    assert await backend.load_artifact(IDENTITY, "report") is None


async def test_old_checkpoint_cannot_resolve_replaced_review(backend, fixture_dir, tmp_path):
    workflow, storage, _ = make_workflow(backend, fixture_dir, tmp_path)
    result = await workflow.run(IDENTITY)
    request = result.get_request_info_events()[0].data
    old_checkpoint = await storage.get_latest(workflow_name="test-ledger")
    await restart(backend, fixture_dir, tmp_path, request, "request_info")
    workflow, _, _ = make_workflow(backend, fixture_dir, tmp_path)
    with pytest.raises(StaleReviewError):
        await workflow.run(
            checkpoint_id=old_checkpoint.checkpoint_id,
            responses={
                request.request_id: HumanReply(
                    identity=IDENTITY, request_id=request.request_id, action="keep_flagged"
                )
            },
        )


async def test_changed_input_invalidates_delivery(backend, fixture_dir, tmp_path):
    order = await backend.load_order(IDENTITY.order_id)
    order.files = order.files[:4]
    order.transactions = order.transactions[:4]
    backend.put_order(order)
    workflow, _, _ = make_workflow(backend, fixture_dir, tmp_path)
    request = (await workflow.run(IDENTITY)).get_request_info_events()[0].data
    order.identity.revision = 2
    backend.put_order(order)
    with pytest.raises(StaleReviewError):
        await restart(
            backend, fixture_dir, tmp_path, request, "approve_delivery", report_version=request.report_version
        )


async def test_invalid_tool_result_cannot_reach_report(backend, fixture_dir, tmp_path):
    original = backend.reconcile

    async def invalid(order, invoices):
        result = await original(order, invoices)
        result.matches[0].amount_minor += 1
        return result

    backend.reconcile = invalid
    workflow, _, _ = make_workflow(backend, fixture_dir, tmp_path)
    with pytest.raises(ModelOutputError):
        await workflow.run(IDENTITY)
    assert await backend.load_artifact(IDENTITY, "report") is None


def test_local_execution_lease_releases_on_exit(tmp_path):
    from app.agents.errors import AgentError
    from app.agents.lease import ExecutionLease

    lock = tmp_path / "execution.lock"
    with ExecutionLease(lock), pytest.raises(AgentError), ExecutionLease(lock):
        pass
    with ExecutionLease(lock):
        pass


@pytest.mark.parametrize("value", ["1,2", "1e3", "9" * 65, "1.005"])
def test_invalid_money_formats_stay_unknown(value):
    assert amount_to_minor(value) is None


async def test_failed_node_retries_from_saved_checkpoint(backend, fixture_dir, tmp_path):
    from app.agents.errors import AgentError

    class FailInvoice(ScriptedRunner):
        async def generate(self, role, prompt, schema, budget, **kwargs):
            if role == "invoice":
                await budget.reserve()
                raise AgentError("simulated transport failure")
            return await super().generate(role, prompt, schema, budget, **kwargs)

    workflow, storage, _ = make_workflow(backend, fixture_dir, tmp_path, runner=FailInvoice(fixture_dir))
    with pytest.raises(AgentError):
        await workflow.run(IDENTITY)
    spent = (await backend.load_artifact(IDENTITY, "usage"))["requests"]
    checkpoint = await storage.get_latest(workflow_name="test-ledger")
    workflow, _, runner = make_workflow(backend, fixture_dir, tmp_path)
    result = await workflow.run(checkpoint_id=checkpoint.checkpoint_id)
    assert result.get_request_info_events()[0].data.kind == "exception"
    assert "supervisor" not in runner.calls
    assert (await backend.load_artifact(IDENTITY, "usage"))["requests"] > spent
