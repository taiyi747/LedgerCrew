"""Explicit MAF graph. No HTTP, database, tax engine, or publication side effects."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import Any

from agent_framework import (
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)

from .config import Settings
from .contracts import (
    AgentDependencies,
    AgentEvent,
    CustomerDraft,
    HumanReply,
    InvoiceExtraction,
    InvoiceRecord,
    ReconciliationAcknowledgement,
    ReconciliationResult,
    ReportDraft,
    ReportNarrative,
    ReviewRequest,
    RunIdentity,
    RunOutcome,
    RunState,
    SupervisorDecision,
)
from .errors import AgentError, ModelOutputError, StaleReviewError
from .runner import MiMoRunner, ModelRunner, RequestBudget


def fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def amount_to_minor(text: str | None) -> int | None:
    if text is None:
        return None
    cleaned = text.strip().removeprefix("￥").removeprefix("¥").removesuffix("元").strip()
    if len(cleaned) > 64 or not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", cleaned):
        return None
    try:
        value = Decimal(cleaned.replace(",", ""))
        if not value.is_finite() or value < 0 or value.as_tuple().exponent < -2:
            return None
        return int(value * 100)
    except InvalidOperation:
        return None


def all_evidence(state: RunState) -> set[str]:
    refs = {f.id for f in state.order.files}
    refs |= {i.id for i in state.invoices}
    refs |= {t.id for t in state.order.transactions}
    refs |= {t.source_file_id for t in state.order.transactions}
    if state.reconciliation:
        refs |= {i.id for i in state.reconciliation.issues}
    return refs


def validate_reconciliation(state: RunState, result: ReconciliationResult) -> None:
    if result.identity != state.order.identity:
        raise ModelOutputError("对账结果属于其他订单、运行或输入版本。")
    invoices = {i.id: i for i in state.invoices}
    transactions = {t.id: t for t in state.order.transactions}
    used_invoices: set[str] = set()
    used_transactions: set[str] = set()
    refs = all_evidence(state)
    if len({i.id for i in result.issues}) != len(result.issues):
        raise ModelOutputError("对账异常标识重复。")
    for match in result.matches:
        invoice, transaction = invoices.get(match.invoice_id), transactions.get(match.transaction_id)
        if invoice is None or transaction is None:
            raise ModelOutputError("对账结果引用不存在的记录。")
        if (
            invoice.needs_review
            or invoice.amount_minor != match.amount_minor
            or transaction.amount_minor != match.amount_minor
        ):
            raise ModelOutputError("未经确认或金额不同的记录不能直接匹配。")
        if match.invoice_id in used_invoices or match.transaction_id in used_transactions:
            raise ModelOutputError("同一票据或流水被重复匹配。")
        if not match.evidence_refs or not set(match.evidence_refs) <= refs:
            raise ModelOutputError("匹配缺少有效来源。")
        used_invoices.add(match.invoice_id)
        used_transactions.add(match.transaction_id)
    for issue in result.issues:
        if (
            not set(issue.invoice_ids) <= invoices.keys()
            or not set(issue.transaction_ids) <= transactions.keys()
        ):
            raise ModelOutputError("异常引用不存在的记录。")
        if not issue.evidence_refs or not set(issue.evidence_refs) <= refs:
            raise ModelOutputError("异常缺少有效来源。")
    for invoice in state.invoices:
        if invoice.needs_review and not any(invoice.id in i.invoice_ids for i in result.issues):
            raise ModelOutputError("未确认票据没有被列入待处理事项。")


class Runtime:
    def __init__(self, deps: AgentDependencies, runner: ModelRunner, max_requests: int):
        self.deps = deps
        self.runner = runner
        self.max_requests = max_requests
        self.budget: RequestBudget | None = None

    def budget_for(self, identity: RunIdentity) -> RequestBudget:
        if self.budget is None:
            self.budget = RequestBudget(self.deps, identity, self.max_requests)
        else:
            self.budget.identity = identity
        return self.budget

    async def emit(self, state: RunState, role: str, status: str, message: str, **data) -> None:
        identity = state.order.identity
        await self.deps.emit_event(
            AgentEvent(
                identity=identity,
                event_id=fingerprint([identity.model_dump(), role, status, message, data]),
                agent=role,
                type=status,
                message=message,
                data=data,
            )
        )

    @asynccontextmanager
    async def step(self, state: RunState, role: str):
        await self.emit(state, role, "started", "开始执行任务")
        try:
            yield
        except Exception as error:
            safe_message = str(error) if isinstance(error, AgentError) else type(error).__name__
            await self.emit(state, role, "failed", safe_message)
            raise
        else:
            await self.emit(state, role, "completed", "任务成果已保存")

    async def save(self, state: RunState, kind: str, payload: dict) -> None:
        await self.deps.save_artifact(
            state.order.identity,
            kind,
            payload,
            fingerprint([kind, state.order.identity.model_dump(), payload]),
        )


class Supervisor(Executor):
    def __init__(self, runtime: Runtime):
        super().__init__(id="supervisor")
        self.runtime = runtime

    @handler
    async def run(self, identity: RunIdentity, ctx: WorkflowContext[RunState]):
        order = await self.runtime.deps.load_order(identity.order_id)
        if order.identity != identity:
            raise StaleReviewError("启动请求与当前订单版本不一致。")
        if len({f.id for f in order.files}) != len(order.files) or len(
            {t.id for t in order.transactions}
        ) != len(order.transactions):
            raise ModelOutputError("输入包含重复记录标识。")
        state = RunState(order=order)
        async with self.runtime.step(state, "supervisor"):
            decision = await self.runtime.runner.generate(
                "supervisor",
                "材料已通过基本校验，请安排票据处理任务。\n" + order.model_dump_json(),
                SupervisorDecision,
                self.runtime.budget_for(identity),
            )
            await self.runtime.save(state, "supervisor", decision.model_dump(mode="json"))
        await ctx.send_message(state)


class ExtractInvoices(Executor):
    def __init__(self, runtime: Runtime):
        super().__init__(id="invoice")
        self.runtime = runtime

    @handler
    async def run(self, state: RunState, ctx: WorkflowContext[RunState]):
        semaphore = asyncio.Semaphore(2)

        async def extract(file):
            async with semaphore:
                data = await self.runtime.deps.read_invoice(state.order.identity.order_id, file.id)
                if len(data) > 5 * 1024 * 1024:
                    raise ModelOutputError("票据图片超过 5 MB。")
                key = "invoice:" + file.id + ":" + hashlib.sha256(data).hexdigest()
                cached = await self.runtime.deps.load_artifact(state.order.identity, key)
                if cached:
                    raw = InvoiceExtraction.model_validate(cached)
                else:
                    raw = await self.runtime.runner.generate(
                        "invoice",
                        "提取这张采购票据。counterparty 读取销售方，金额读取价税合计。"
                        "金额保留原始文本；只有模糊或无法读取的字段才为 null 并列入 uncertain_fields。"
                        "uncertain_fields 是图像可读性检查，不是商户真实性判断；合成样例中清晰可读的字段正常提取。",
                        InvoiceExtraction,
                        self.runtime.budget_for(state.order.identity),
                        image=(data, file.mime_type),
                    )
                    await self.runtime.save(state, key, raw.model_dump(mode="json"))
                amount = amount_to_minor(raw.amount_text)
                missing = any(v is None for v in (raw.invoice_number, raw.date, raw.counterparty, amount))
                return InvoiceRecord(
                    **raw.model_dump(),
                    identity=state.order.identity,
                    id="invoice-" + file.id,
                    source_file_id=file.id,
                    amount_minor=amount,
                    needs_review=missing or bool(raw.uncertain_fields),
                )

        async with self.runtime.step(state, "invoice"):
            tasks = [asyncio.create_task(extract(f)) for f in state.order.files]
            try:
                state.invoices = await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            await self.runtime.save(
                state, "invoices", {"items": [i.model_dump(mode="json") for i in state.invoices]}
            )
        await ctx.send_message(state)


class Reconcile(Executor):
    def __init__(self, runtime: Runtime):
        super().__init__(id="reconciliation")
        self.runtime = runtime

    @handler
    async def run(self, state: RunState, ctx: WorkflowContext[RunState]):
        result: ReconciliationResult | None = None

        async def reconcile_transactions() -> str:
            """核对当前订单票据和流水，返回有来源的确定性结果。不得自行计算替代此工具。"""
            nonlocal result
            if result is None:
                cached = await self.runtime.deps.load_artifact(
                    state.order.identity,
                    "reconciliation:" + str(state.order.identity.revision),
                )
                candidate = (
                    ReconciliationResult.model_validate(cached)
                    if cached
                    else await self.runtime.deps.reconcile(state.order, state.invoices)
                )
                validate_reconciliation(state, candidate)
                await self.runtime.save(
                    state,
                    "reconciliation:" + str(state.order.identity.revision),
                    candidate.model_dump(mode="json"),
                )
                await self.runtime.emit(
                    state,
                    "reconciliation",
                    "completed",
                    "对账工具已返回实际结果",
                    result=candidate.model_dump(mode="json"),
                )
                result = candidate
            return result.model_dump_json()

        async with self.runtime.step(state, "reconciliation"):
            await self.runtime.runner.generate(
                "reconciliation",
                "调用 reconcile_transactions 后用 summary 简述已执行的检查。",
                ReconciliationAcknowledgement,
                self.runtime.budget_for(state.order.identity),
                tools=[reconcile_transactions],
            )
            if result is None:
                raise ModelOutputError("核对 Agent 未调用对账工具，不能继续交付。")
            state.reconciliation = result
        await ctx.send_message(state)


def validate_reply(request: ReviewRequest, reply: HumanReply) -> None:
    if reply.identity != request.identity or reply.request_id != request.request_id:
        raise StaleReviewError("人工回复不属于当前订单、运行、版本或待办。")
    if reply.action not in request.allowed_actions:
        raise StaleReviewError("当前待办不允许该操作。")
    if request.kind == "delivery" and reply.report_version != request.report_version:
        raise StaleReviewError("交付审批属于过期或错误的报告版本。")


async def require_latest_review(runtime: Runtime, request: ReviewRequest) -> None:
    latest = await runtime.deps.load_artifact(request.identity, "review")
    if latest is None or ReviewRequest.model_validate(latest) != request:
        raise StaleReviewError("该待办已被替换，不能从旧检查点批准或修改成果。")


async def ask(runtime: Runtime, state: RunState, ctx, kind: str, question: str, actions: list) -> None:
    request = ReviewRequest(
        identity=state.order.identity,
        request_id=fingerprint([state.order.identity.model_dump(), kind, state.report_version]),
        kind=kind,
        question=question,
        allowed_actions=actions,
        evidence_refs=sorted(all_evidence(state)),
        report_version=state.report_version if kind == "delivery" else None,
    )
    ctx.set_state("ledger_state", state.model_dump(mode="json"))
    await runtime.save(state, "review", request.model_dump(mode="json"))
    await runtime.emit(
        state,
        "delivery" if kind == "delivery" else "customer_service",
        "waiting",
        question,
        review=request.model_dump(mode="json"),
    )
    await ctx.request_info(request, HumanReply, request_id=request.request_id)


class CustomerService(Executor):
    def __init__(self, runtime: Runtime):
        super().__init__(id="customer_service")
        self.runtime = runtime

    @handler
    async def run(self, state: RunState, ctx: WorkflowContext[RunState]):
        if not state.reconciliation:
            raise AgentError("缺少对账结果。")
        if not state.reconciliation.issues:
            state.next_step = "report"
            await ctx.send_message(state)
            return
        async with self.runtime.step(state, "customer_service"):
            invoice_map = {i.id: i for i in state.invoices}
            transaction_map = {t.id: t for t in state.order.transactions}
            questions = []
            for issue in state.reconciliation.issues:
                questions.append(
                    {
                        "kind": issue.kind,
                        "description": issue.description,
                        "invoices": [
                            {
                                "number": invoice_map[key].invoice_number,
                                "seller": invoice_map[key].counterparty,
                                "amount_yuan": None
                                if invoice_map[key].amount_minor is None
                                else f"{Decimal(invoice_map[key].amount_minor) / 100:.2f}",
                            }
                            for key in issue.invoice_ids
                        ],
                        "payments": [
                            {
                                "counterparty": transaction_map[key].counterparty,
                                "amount_yuan": f"{Decimal(transaction_map[key].amount_minor) / 100:.2f}",
                            }
                            for key in issue.transaction_ids
                        ],
                        "difference_yuan": None
                        if issue.difference_minor is None
                        else f"{Decimal(issue.difference_minor) / 100:.2f}",
                        "evidence_refs": issue.evidence_refs,
                    }
                )
            draft = await self.runtime.runner.generate(
                "customer_service",
                "根据异常生成一段客户可读的询问引言，供老板审核。question 禁止出现任何阿拉伯数字、"
                "票据号码、系统标识和金额；精确明细由程序附加。不要编号列举，直接描述需要核实和补充的内容。"
                "可能原因只能作为问题，不可断言已确认。evidence_refs 仅使用给出的引用。\n"
                + json.dumps(questions, ensure_ascii=False),
                CustomerDraft,
                self.runtime.budget_for(state.order.identity),
            )
            if not set(draft.evidence_refs) <= all_evidence(state):
                raise ModelOutputError("询问草稿引用不存在的证据。")
            await self.runtime.save(state, "customer_draft", draft.model_dump(mode="json"))
        # Financial facts and document numbers are rendered from backend data,
        # so model prose cannot silently change an amount or invoice identifier.
        lines = []
        for item in questions:
            descriptions = [item["description"]]
            for invoice in item["invoices"]:
                descriptions.append(
                    f"票据 {invoice['number'] or '号码待确认'}，"
                    f"交易方 {invoice['seller'] or '待确认'}，"
                    f"票据金额 {invoice['amount_yuan'] or '待确认'} 元"
                )
            for payment in item["payments"]:
                descriptions.append(
                    f"付款交易方 {payment['counterparty']}，付款金额 {payment['amount_yuan']} 元"
                )
            if item["difference_yuan"] is not None:
                descriptions.append(f"差额 {item['difference_yuan']} 元，原因待核实")
            lines.append("；".join(descriptions))
        await ask(
            self.runtime,
            state,
            ctx,
            "exception",
            draft.question + "\n" + "\n".join(lines),
            ["request_info", "keep_flagged"],
        )

    @response_handler
    async def respond(self, request: ReviewRequest, reply: HumanReply, ctx: WorkflowContext[RunState]):
        validate_reply(request, reply)
        await require_latest_review(self.runtime, request)
        state = RunState.model_validate(ctx.get_state("ledger_state"))
        current = await self.runtime.deps.load_order(request.identity.order_id)
        if reply.action == "submit_information":
            if (
                current.identity.order_id != request.identity.order_id
                or current.identity.run_id != request.identity.run_id
                or current.identity.revision <= request.identity.revision
            ):
                raise StaleReviewError("补充材料必须先保存为同一运行的新输入版本。")
            state.order = current
            state.invoices = []
            state.reconciliation = None
            state.report = None
            state.next_step = "extract"
            await ctx.send_message(state)
            return
        if current.identity != request.identity:
            raise StaleReviewError("输入已改变，请先重新核对。")
        if reply.action == "request_info":
            await ask(
                self.runtime,
                state,
                ctx,
                "customer",
                reply.comment or request.question,
                ["submit_information"],
            )
        else:
            if reply.comment:
                state.order.customer_notes.append("老板保留异常的说明：" + reply.comment)
            state.next_step = "report"
            await ctx.send_message(state)


class Delivery(Executor):
    def __init__(self, runtime: Runtime):
        super().__init__(id="delivery")
        self.runtime = runtime

    @handler
    async def run(self, state: RunState, ctx: WorkflowContext[RunState, RunOutcome]):
        if not state.reconciliation:
            raise AgentError("缺少对账结果，不能生成报告。")
        async with self.runtime.step(state, "delivery"):
            narrative = await self.runtime.runner.generate(
                "delivery",
                "为核对结果撰写说明。所有叙述禁止写数字或金额，数值由结构化明细展示。"
                "逐项保留未解决事项，不声称异常已解决。evidence_ref 仅引用提供的来源标识。\n"
                + json.dumps(
                    {
                        "result": state.reconciliation.model_dump(mode="json"),
                        "notes": state.order.customer_notes,
                        "feedback": state.report_feedback,
                    },
                    ensure_ascii=False,
                ),
                ReportNarrative,
                self.runtime.budget_for(state.order.identity),
            )
            if not {n.evidence_ref for n in narrative.evidence_notes} <= all_evidence(state):
                raise ModelOutputError("报告引用不存在的来源。")
            state.report_version += 1
            state.report = ReportDraft(
                identity=state.order.identity,
                report_version=state.report_version,
                narrative=narrative,
                reconciliation=state.reconciliation,
                unresolved_issue_ids=[i.id for i in state.reconciliation.issues],
                customer_notes=state.order.customer_notes,
            )
            await self.runtime.save(state, "report", state.report.model_dump(mode="json"))
        await ask(
            self.runtime,
            state,
            ctx,
            "delivery",
            "请审核本版本报告，批准后由后端发布。",
            ["approve_delivery", "revise_report"],
        )

    @response_handler
    async def respond(
        self, request: ReviewRequest, reply: HumanReply, ctx: WorkflowContext[RunState, RunOutcome]
    ):
        validate_reply(request, reply)
        await require_latest_review(self.runtime, request)
        state = RunState.model_validate(ctx.get_state("ledger_state"))
        current = await self.runtime.deps.load_order(request.identity.order_id)
        if current.identity != request.identity or not state.report:
            raise StaleReviewError("输入已改变或报告不存在，必须重新生成并审核。")
        if reply.action == "revise_report":
            state.report_feedback = reply.comment
            await ctx.send_message(state)
            return
        outcome = RunOutcome(
            identity=state.order.identity,
            status="delivery_approved",
            report=state.report,
            approval_request_id=request.request_id,
        )
        await self.runtime.save(state, "approval", outcome.model_dump(mode="json"))
        await self.runtime.emit(
            state,
            "delivery",
            "delivery_approved",
            "报告已获得人工批准，由后端发布。",
            report_version=state.report_version,
            request_id=request.request_id,
        )
        await ctx.yield_output(outcome)


def build_workflow(
    deps: AgentDependencies,
    checkpoint_storage,
    workflow_name: str,
    *,
    runner: ModelRunner | None = None,
    max_requests: int | None = None,
) -> Workflow:
    """Pass runner only for explicit test adapters. Production defaults to real MiMo."""
    if runner is None:
        settings = Settings.from_env()
        runner = MiMoRunner(settings)
        max_requests = settings.max_requests if max_requests is None else max_requests
    runtime = Runtime(deps, runner, 64 if max_requests is None else max_requests)
    supervisor, invoice, reconciliation, service, delivery = (
        Supervisor(runtime),
        ExtractInvoices(runtime),
        Reconcile(runtime),
        CustomerService(runtime),
        Delivery(runtime),
    )
    return (
        WorkflowBuilder(
            start_executor=supervisor,
            checkpoint_storage=checkpoint_storage,
            name=workflow_name,
            max_iterations=64,
        )
        .add_edge(supervisor, invoice)
        .add_edge(invoice, reconciliation)
        .add_edge(reconciliation, service)
        .add_edge(service, invoice, condition=lambda state: state.next_step == "extract")
        .add_edge(service, delivery, condition=lambda state: state.next_step == "report")
        # Only the explicit human "revise_report" response sends this edge;
        # max_iterations and the persisted request budget also bound rework.
        .add_edge(delivery, delivery)
        .build()
    )
