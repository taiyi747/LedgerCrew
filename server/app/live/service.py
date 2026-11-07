from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError
from app.db.types import utc_now
from app.live.contracts import TASK_ROLE, Assignment
from app.live.models import Delegation, OrderMessage, WorkflowArtifact, WorkflowRun
from app.models import (
    BankTransaction,
    ExceptionDecision,
    ExceptionSupplement,
    InvoiceRecord,
    Order,
    ReportReviewAction,
    ReportVersion,
    StatementImport,
    Studio,
    UploadedFile,
    WorkflowEvent,
)
from app.repositories import reconciliation as reconciliation_repo
from app.services.access import order_for_user


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


async def event(session, order_id, name, payload=None):
    session.add(WorkflowEvent(order_id=order_id, event_type=name, payload=payload or {}))


async def current_run(session, order_id, kind="processing"):
    return await session.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.order_id == order_id, WorkflowRun.kind == kind)
        .order_by(WorkflowRun.created_at.desc())
    )


async def guard_inputs(session, order_id, expected_revision=None):
    order = await session.get(Order, order_id)
    if expected_revision is not None and order.input_revision != expected_revision:
        raise AppError("stale_revision", "材料版本已变化，请刷新后重试。", 409)
    run = await current_run(session, order_id)
    if run and run.status in {"queued", "running"}:
        raise AppError("order_busy", "当前正在处理材料，请等待本轮完成后再修改。", 409)


async def touch_inputs(session, order_id, *, wake=False, force_wake=True):
    order = await session.get(Order, order_id)
    await session.execute(
        update(Order).where(Order.id == order_id).values(input_revision=Order.input_revision + 1)
    )
    await session.refresh(order, ["input_revision"])
    if wake:
        await wake_supervisor(session, order_id, force=force_wake)
    await event(session, order_id, "order.inputs_changed", {"input_revision": order.input_revision})


async def wake_supervisor(session, order_id, *, force=True):
    run = await current_run(session, order_id)
    order = await session.get(Order, order_id)
    if run and run.status == "paused":
        if not force and run.wait_reason == "waiting_owner":
            batch = await reconciliation_repo.latest_batch(session, order_id)
            tickets = await reconciliation_repo.list_tickets(session, batch.id) if batch else []
            if any(t.status not in {"resolved", "accepted_unresolved"} for t in tickets) and not any(
                t.status == "waiting_customer" for t in tickets
            ):
                return
        run.status, run.stage, run.wait_reason = "queued", "supervisor", None
        if order.status != "delivered":
            order.status = "processing"
        run.input_revision = order.input_revision
        run.lease_token = None
        run.lease_expires_at = None
        await event(session, order_id, "workflow.queued", {"workflow_run_id": run.id})


async def artifact(session, run_id, kind):
    return await session.scalar(
        select(WorkflowArtifact)
        .where(
            WorkflowArtifact.workflow_run_id == run_id,
            WorkflowArtifact.kind == kind,
        )
        .order_by(WorkflowArtifact.created_at.desc(), WorkflowArtifact.id.desc())
    )


async def save_artifact(session, run, kind, payload, key):
    key = fingerprint(key)
    existing = await session.scalar(
        select(WorkflowArtifact).where(
            WorkflowArtifact.workflow_run_id == run.id, WorkflowArtifact.operation_key == key
        )
    )
    if existing:
        if existing.payload != payload:
            raise AppError("artifact_conflict", "相同操作对应不同成果。", 409)
        return existing
    record = WorkflowArtifact(
        workflow_run_id=run.id,
        kind=kind,
        payload=payload,
        operation_key=key,
        input_revision=run.input_revision,
    )
    session.add(record)
    await session.flush()
    return record


async def snapshot(session, run_id):
    run = await session.get(WorkflowRun, run_id)
    if not run:
        raise AppError("not_found", "Workflow not found", 404)
    order = await session.get(Order, run.order_id)
    studio = await session.get(Studio, order.studio_id)
    files = list(
        (
            await session.scalars(
                select(UploadedFile)
                .where(
                    UploadedFile.order_id == order.id,
                    UploadedFile.is_active.is_(True),
                    UploadedFile.validation_status == "valid",
                )
                .order_by(UploadedFile.created_at)
            )
        ).all()
    )
    images = [f for f in files if f.file_category == "invoice_image"]
    invoices = list(
        (
            await session.scalars(
                select(InvoiceRecord)
                .where(
                    InvoiceRecord.order_id == order.id,
                    InvoiceRecord.source_file_id.in_([f.id for f in images]),
                )
                .order_by(InvoiceRecord.created_at, InvoiceRecord.id)
            )
        ).all()
    )
    transactions = list(
        (
            await session.scalars(
                select(BankTransaction)
                .where(BankTransaction.order_id == order.id)
                .order_by(BankTransaction.row_number, BankTransaction.id)
            )
        ).all()
    )
    imported = list(
        (
            await session.scalars(
                select(StatementImport)
                .where(StatementImport.order_id == order.id)
                .order_by(StatementImport.created_at.desc())
            )
        ).all()
    )
    valid_imports = [i for i in imported if i.failed_rows == 0 and i.success_rows > 0]
    csv_ids = {f.id for f in files if f.file_category == "bank_statement_csv"}
    valid_imports = [i for i in valid_imports if i.uploaded_file_id in csv_ids]
    signature = fingerprint(
        {
            "files": [(f.id, f.sha256) for f in files],
            "period": [order.period_start, order.period_end],
            "studio": studio.name,
            "imports": [i.id for i in valid_imports],
        }
    )
    batch = await reconciliation_repo.latest_batch(session, order.id)
    batch_artifact = await artifact(session, run.id, "reconciliation")
    batch_fresh = bool(
        batch
        and batch_artifact
        and batch_artifact.payload.get("signature") == signature
        and batch_artifact.payload.get("batch_id") == batch.id
    )
    tickets = await reconciliation_repo.list_tickets(session, batch.id) if batch else []
    # 证据本身只是校验结果，老板需要知道它对应"哪张表第几行"，因此随异常单一起
    # 下发来源定位：表名、序号/行号、记录标识与原始文件。
    invoice_by_id = {item.id: item for item in invoices}
    invoice_ordinal = {item.id: index for index, item in enumerate(invoices, start=1)}
    transaction_by_id = {item.id: item for item in transactions}
    file_names = {f.id: f.original_filename for f in files}

    def ticket_location(ticket):
        invoice = invoice_by_id.get(ticket.invoice_id) if ticket.invoice_id else None
        if invoice:
            return {
                "table": "invoice_records",
                "table_label": "票据记录",
                "row_number": invoice_ordinal[invoice.id],
                "row_unit": "张",
                "record_id": invoice.id,
                "record_label": invoice.invoice_number
                or file_names.get(invoice.source_file_id)
                or invoice.id[:8],
                "source_file": file_names.get(invoice.source_file_id),
                "occurred_on": str(invoice.issue_date) if invoice.issue_date else None,
            }
        transaction = transaction_by_id.get(ticket.transaction_id) if ticket.transaction_id else None
        if transaction:
            return {
                "table": "bank_transactions",
                "table_label": "银行流水",
                "row_number": transaction.row_number,
                "row_unit": "行",
                "record_id": transaction.id,
                "record_label": transaction.external_id
                or transaction.normalized_counterparty
                or transaction.id[:8],
                "source_file": None,
                "occurred_on": str(transaction.transaction_date),
            }
        return None

    supplements = list(
        (
            await session.scalars(
                select(ExceptionSupplement)
                .where(ExceptionSupplement.order_id == order.id)
                .order_by(ExceptionSupplement.created_at)
            )
        ).all()
    )
    decisions = list(
        (
            await session.scalars(
                select(ExceptionDecision)
                .where(ExceptionDecision.order_id == order.id)
                .order_by(ExceptionDecision.created_at)
            )
        ).all()
    )
    report = await session.scalar(
        select(ReportVersion).where(ReportVersion.order_id == order.id).order_by(ReportVersion.version.desc())
    )
    report_fresh = bool(
        report
        and batch_fresh
        and report.source_revision == order.input_revision
        and report.reconciliation_batch_id == batch.id
    )
    if (
        report
        and report.status == "draft"
        and await session.scalar(
            select(ReportReviewAction.id).where(
                ReportReviewAction.report_id == report.id, ReportReviewAction.action == "rejected"
            )
        )
    ):
        report_fresh = False
    eligible = []
    if not await artifact(session, run.id, "intake"):
        eligible.append("intake")
    invoice_ids = {i.source_file_id for i in invoices}
    pending_images = [f.id for f in images if f.id not in invoice_ids]
    if valid_imports and len(csv_ids) == 1:
        if pending_images:
            eligible.append("invoice_batch")
        elif not batch_fresh:
            eligible.append("reconcile_order")
    current_risk = await artifact(session, run.id, "risk")
    current_questions = await artifact(session, run.id, "questions")
    if batch_fresh:
        unsettled = [t for t in tickets if t.status not in {"resolved", "accepted_unresolved"}]
        if tickets and (not current_risk or current_risk.input_revision != order.input_revision):
            eligible.append("risk_summary")
        if unsettled and (not current_questions or current_questions.payload.get("batch_id") != batch.id):
            eligible.append("questions")
        if not unsettled and not report_fresh and (not tickets or "risk_summary" not in eligible):
            eligible.append("report_draft")
    previous = list(
        (
            await session.scalars(
                select(Delegation).where(Delegation.workflow_run_id == run.id).order_by(Delegation.created_at)
            )
        ).all()
    )
    failed_tasks = [
        {"id": d.id, "task_type": d.task_type, "error": d.error, "attempt_count": d.attempt_count}
        for d in previous
        if d.status == "failed"
    ]
    exhausted = {d.task_type for d in previous if d.status == "failed" and d.attempt_count >= 3}
    eligible = [task for task in eligible if task not in exhausted]
    chat_done = await artifact(session, run.id, "chat_answer") if run.kind == "chat" else None
    source_message = await session.get(OrderMessage, run.source_message_id) if run.source_message_id else None
    if run.kind == "chat":
        eligible = [] if chat_done else ["answer_question"]
    return {
        "run_id": run.id,
        "kind": run.kind,
        "chat_done": bool(chat_done),
        "customer_question": source_message.content if source_message else None,
        "failed_tasks": failed_tasks,
        "order_id": order.id,
        "input_revision": order.input_revision,
        "company_name": studio.name,
        "period_start": str(order.period_start),
        "period_end": str(order.period_end),
        "files": [
            {
                "id": f.id,
                "name": f.original_filename,
                "category": f.file_category,
                "mime_type": f.mime_type,
                "sha256": f.sha256,
            }
            for f in files
        ],
        "image_ids": [f.id for f in images],
        "pending_image_ids": pending_images,
        "csv_ready": bool(valid_imports) and len(csv_ids) == 1,
        "financial_signature": signature,
        "batch_id": batch.id if batch else None,
        "batch_fresh": batch_fresh,
        "financial_summary": {
            k: getattr(batch, k)
            for k in ("income_total_cents", "expense_total_cents", "net_cash_change_cents")
        }
        if batch
        else None,
        "matched_count": batch.matched_count if batch else 0,
        "exceptions": [
            {
                "id": t.id,
                "exception_no": t.exception_no,
                "type": t.exception_type,
                "status": t.status,
                "difference_cents": t.difference_cents,
                "related_amount_cents": t.related_amount_cents,
                "evidence": t.evidence_json,
                "location": ticket_location(t),
            }
            for t in tickets
        ],
        "customer_supplements": [
            {"exception_id": s.exception_id, "explanation": s.explanation, "file_id": s.file_id}
            for s in supplements
        ],
        "owner_decisions": [
            {
                "exception_id": d.exception_id,
                "decision": d.decision,
                "reason": d.reason,
                "target_version": d.target_version,
            }
            for d in decisions
        ],
        "report": {"id": report.id, "version": report.version, "status": report.status, "fresh": report_fresh}
        if report
        else None,
        "eligible_tasks": eligible,
        "customer_waiting": any(t.status == "waiting_customer" for t in tickets),
        "all_exceptions_settled": bool(batch_fresh)
        and all(t.status in {"resolved", "accepted_unresolved"} for t in tickets),
    }


async def start_run(session, order_id, principal, key, expected_revision, *, commit=True):
    order = await order_for_user(session, order_id, principal)
    if order.input_revision != expected_revision:
        raise AppError("stale_revision", "材料版本已变化，请刷新后重试。", 409)
    # Model request ceiling for one processing run. Every recognised image or
    # document costs one or more requests; 300 covers a couple hundred materials
    # plus workflow overhead and still bounds a runaway loop. Raise the constant
    # when bigger batches arrive.
    request_limit = 300
    existing = await session.scalar(
        select(WorkflowRun).where(WorkflowRun.order_id == order_id, WorkflowRun.idempotency_key == key)
    )
    if existing:
        return existing
    active = await current_run(session, order_id)
    if active and active.status in {"queued", "running", "paused", "failed"}:
        if active.status == "paused" and active.input_revision != order.input_revision:
            active.request_limit = max(active.request_limit, request_limit)
            await wake_supervisor(session, order_id)
            if commit:
                await session.commit()
        return active
    run = WorkflowRun(
        order_id=order_id,
        kind="processing",
        status="queued",
        stage="supervisor",
        input_revision=order.input_revision,
        idempotency_key=key,
        created_by=principal.user_id,
        request_limit=request_limit,
    )
    session.add(run)
    try:
        await session.flush()
    except IntegrityError:
        if not commit:
            raise
        await session.rollback()
        winner = await current_run(session, order_id)
        if winner:
            return winner
        raise
    state = await snapshot(session, run.id)
    if not state["csv_ready"]:
        if commit:
            await session.rollback()
        raise AppError("missing_statement", "请上传并成功导入一份无错误行的 CSV 流水。", 422)
    order.status = "processing"
    await event(session, order.id, "workflow.queued", {"workflow_run_id": run.id})
    if commit:
        await session.commit()
    else:
        await session.flush()
    return run


async def delegate(session, run, decision_id, assignment: Assignment, expected_revision):
    state = await snapshot(session, run.id)
    if state["input_revision"] != expected_revision:
        raise AppError("stale_revision", "调度快照已变化。", 409)
    if (
        assignment.task_type not in state["eligible_tasks"]
        or TASK_ROLE[assignment.task_type] != assignment.agent_role
    ):
        raise AppError("invalid_delegation", "任务角色或前置成果不满足要求。", 409)
    refs = {f["id"] for f in state["files"]} | {t["id"] for t in state["exceptions"]}
    if state["batch_id"]:
        refs.add(state["batch_id"])
    if not set(assignment.input_refs) <= refs:
        raise AppError("invalid_delegation_scope", "派单引用不属于当前订单。", 422)
    revision_key = (
        state["financial_signature"]
        if assignment.task_type in {"invoice_batch", "reconcile_order"}
        else str(expected_revision)
    )
    if assignment.task_type == "report_draft":
        revision_key += ":report:" + str(state["report"]["version"] + 1 if state["report"] else 1)
    operation = fingerprint([assignment.task_type, revision_key])
    existing = await session.scalar(
        select(Delegation).where(Delegation.workflow_run_id == run.id, Delegation.operation_key == operation)
    )
    if existing:
        if existing.status == "failed":
            if existing.attempt_count >= 3:
                raise AppError("task_retry_limit", "该任务已失败三次，请人工处理。", 409)
            existing.status, existing.error = "queued", None
        return existing
    record = Delegation(
        workflow_run_id=run.id,
        order_id=run.order_id,
        decision_id=decision_id,
        input_revision=expected_revision,
        operation_key=operation,
        **assignment.model_dump(),
    )
    session.add(record)
    await session.flush()
    await event(
        session,
        run.order_id,
        "supervisor.delegated",
        {
            "workflow_run_id": run.id,
            "delegation_id": record.id,
            "decision_id": decision_id,
            "agent_role": record.agent_role,
            "task_type": record.task_type,
            "goal": record.goal,
        },
    )
    return record


async def claim_run(session, kind, token):
    now = utc_now()
    candidate = await session.scalar(
        select(WorkflowRun)
        .where(
            WorkflowRun.kind == kind,
            (WorkflowRun.status == "queued")
            | ((WorkflowRun.status == "running") & (WorkflowRun.lease_expires_at < now)),
        )
        .order_by(WorkflowRun.created_at)
        .limit(1)
    )
    if candidate is None:
        return None
    result = await session.execute(
        update(WorkflowRun)
        .where(
            WorkflowRun.id == candidate.id,
            (WorkflowRun.status == "queued")
            | ((WorkflowRun.status == "running") & (WorkflowRun.lease_expires_at < now)),
        )
        .values(
            status="running",
            stage="supervisor" if kind == "processing" else "customer_reception",
            lease_token=token,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=60),
            error=None,
        )
    )
    await session.commit()
    return candidate.id if result.rowcount == 1 else None
