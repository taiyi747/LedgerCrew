import hashlib
import html
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import ReportDraft as WorkflowReportDraft
from app.core.exceptions import AppError
from app.core.security import Principal, assert_owner
from app.db.types import utc_now
from app.integrations.agents.contracts import ReportDraftInput, ReportDraftOutput
from app.models import (
    AgentRun,
    AgentTask,
    AuditLog,
    BankTransaction,
    ExceptionSupplement,
    InvoiceRecord,
    ReconciliationBatch,
    ReconciliationMatch,
    ReportReviewAction,
    ReportVersion,
    UploadedFile,
    WorkflowEvent,
)
from app.repositories import delivery as delivery_repo
from app.repositories import reconciliation as reconciliation_repo
from app.services import order_state
from app.services.access import order_for_user


def _content_hash(report: ReportVersion) -> str:
    content = {
        "order_id": report.order_id, "version": report.version,
        "reconciliation_batch_id": report.reconciliation_batch_id,
        "report_content": report.report_content,
        "financial_summary": report.financial_summary,
        "reconciliation_summary": report.reconciliation_summary,
        "exception_snapshot": report.exception_snapshot,
        "evidence_references": report.evidence_references,
        "unresolved_items": report.unresolved_items,
    }
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _exception_snapshot(session: AsyncSession, batch_id: str) -> list[dict]:
    result = []
    for ticket in await reconciliation_repo.list_tickets(session, batch_id):
        supplements = await delivery_repo.list_supplements(session, ticket.id)
        decisions = await delivery_repo.list_decisions(session, ticket.id)
        last_change = max([ticket.updated_at] + [item.created_at for item in supplements + decisions])
        result.append({
            "exception_id": ticket.id, "exception_no": ticket.exception_no,
            "exception_type": ticket.exception_type, "status": ticket.status,
            "invoice_id": ticket.invoice_id, "transaction_id": ticket.transaction_id,
            "related_amount_cents": ticket.related_amount_cents,
            "difference_cents": ticket.difference_cents,
            "business_classification": ticket.business_classification,
            "evidence": ticket.evidence_json,
            "supplement_ids": [item.id for item in supplements],
            "decision_ids": [item.id for item in decisions],
            "last_change_at": last_change.isoformat(),
        })
    return result


async def _validate_evidence_references(session: AsyncSession, order_id: str,
                                        batch_id: str, references: list[str]) -> None:
    if not references:
        return
    allowed: set[str] = set()
    for model in (UploadedFile, InvoiceRecord, BankTransaction, ExceptionSupplement):
        allowed.update((await session.scalars(select(model.id).where(model.order_id == order_id))).all())
    allowed.update((await session.scalars(select(ReconciliationMatch.id)
                                          .where(ReconciliationMatch.batch_id == batch_id))).all())
    tickets = await reconciliation_repo.list_tickets(session, batch_id)
    allowed.update(item.id for item in tickets)
    if not set(references) <= allowed:
        raise AppError("invalid_report_evidence", "Evidence reference must identify a record in this order", 422)


async def create_from_agent_task(session: AsyncSession, task_id: str) -> ReportVersion:
    """Trusted integration entry; validated Agent text never supplies financial totals."""
    existing = await delivery_repo.report_from_task(session, task_id)
    if existing is not None:
        return existing
    task = await session.get(AgentTask, task_id)
    if task is None or task.agent_name != "risk_delivery" or task.task_type != "report_draft" or task.status != "succeeded":
        raise AppError("invalid_report_source", "A succeeded report_draft task is required", 422)
    source = ReportDraftInput.model_validate(task.input_data)
    output = ReportDraftOutput.model_validate(task.output_data)
    if source.order_id != task.order_id or output.order_id != task.order_id or output.report_version != source.report_version:
        raise AppError("invalid_report_source", "Report task identity or version differs", 422)
    if not set(output.evidence_references) <= set(source.evidence_references):
        raise AppError("invalid_report_evidence", "Output references must be present in task input", 422)
    next_version = await delivery_repo.next_report_version(session, task.order_id)
    if output.report_version != next_version:
        raise AppError("invalid_report_version", "Report version must be the next version for this order", 409)
    batch = await reconciliation_repo.latest_batch(session, task.order_id)
    if batch is None or batch.id != source.reconciliation_summary.batch_id:
        raise AppError("stale_report_source", "Report must use the latest reconciliation batch", 409)
    await _validate_evidence_references(session, task.order_id, batch.id, output.evidence_references)
    financial = {
        "income_total_cents": batch.income_total_cents,
        "expense_total_cents": batch.expense_total_cents,
        "net_cash_change_cents": batch.net_cash_change_cents,
    }
    if financial != source.financial_summary.model_dump():
        raise AppError("invalid_report_source", "Financial summary differs from backend calculation", 422)
    snapshot = await _exception_snapshot(session, batch.id)
    if {item["exception_id"] for item in snapshot} != set(source.reconciliation_summary.exception_ids):
        raise AppError("stale_report_source", "Exception set changed after the Agent task was created", 409)
    if any(datetime.fromisoformat(item["last_change_at"]) > task.created_at for item in snapshot):
        raise AppError("stale_report_source", "Exception changed after the Agent task was created", 409)
    source_exceptions = {item.exception_id: item for item in source.exception_summary}
    if len(source_exceptions) != len(snapshot) or any(
        item["exception_id"] not in source_exceptions or
        source_exceptions[item["exception_id"]].status != item["status"] or
        source_exceptions[item["exception_id"]].exception_type != item["exception_type"] or
        source_exceptions[item["exception_id"]].related_amount_cents != item["related_amount_cents"] or
        source_exceptions[item["exception_id"]].difference_cents != item["difference_cents"]
        for item in snapshot
    ):
        raise AppError("stale_report_source", "Exception details changed after the Agent task was created", 409)
    required_disclosures = [f"{item['exception_no']}: {item['exception_type']} ({item['status']})"
                            for item in snapshot if item["status"] != "resolved"]
    unresolved = list(dict.fromkeys(output.unresolved_items + required_disclosures))
    evidence_references = list(dict.fromkeys(
        output.evidence_references + source.reconciliation_summary.match_ids +
        source.reconciliation_summary.exception_ids))
    report = ReportVersion(
        order_id=task.order_id, version=next_version, status="draft", source_task_id=task.id,
        reconciliation_batch_id=batch.id, report_content=output.report_content,
        financial_summary=financial,
        reconciliation_summary={
            "matched_count": batch.matched_count, "unmatched_count": batch.unmatched_count,
            "exception_count": batch.exception_count,
            "match_ids": source.reconciliation_summary.match_ids,
            "exception_ids": source.reconciliation_summary.exception_ids,
        },
        exception_snapshot=snapshot, evidence_references=evidence_references,
        unresolved_items=unresolved, content_hash="",
    )
    report.content_hash = _content_hash(report)
    session.add(report)
    await session.flush()
    for previous in await delivery_repo.list_reports(session, task.order_id):
        if previous.id != report.id and previous.status in {"draft", "in_review", "approved"}:
            previous.status = "superseded"
    session.add(AuditLog(order_id=task.order_id, actor_type="agent_adapter", actor_id=task.id,
                         action="report.created", entity_type="report_version", entity_id=report.id,
                         details={"version": report.version, "content_hash": report.content_hash}))
    if next_version > 1:
        session.add(AuditLog(order_id=task.order_id, actor_type="agent_adapter", actor_id=task.id,
                             action="report.modified", entity_type="report_version", entity_id=report.id,
                             details={"version": report.version}))
    session.add(WorkflowEvent(order_id=task.order_id, run_id=task.run_id, task_id=task.id,
                              event_type="report.created", payload={"report_id": report.id, "version": report.version}))
    await session.commit()
    return report


async def create_from_workflow(session: AsyncSession, task_id: str,
                               draft: WorkflowReportDraft) -> ReportVersion:
    """Create an auditable report from the existing MAF graph and backend reconciliation."""
    existing = await session.scalar(select(ReportVersion).where(
        ReportVersion.workflow_task_id == task_id,
        ReportVersion.workflow_report_version == draft.report_version))
    if existing is not None:
        return existing
    task = await session.get(AgentTask, task_id)
    if (task is None or task.task_type != "full_workflow" or task.order_id != draft.identity.order_id
            or task.run_id != draft.identity.run_id):
        raise AppError("invalid_workflow_report", "Workflow report identity differs", 422)
    batch = await session.scalar(select(ReconciliationBatch).where(
        ReconciliationBatch.workflow_task_id == task_id))
    latest = await reconciliation_repo.latest_batch(session, task.order_id)
    if batch is None or latest is None or latest.id != batch.id:
        raise AppError("stale_workflow_report", "Workflow reconciliation is not current", 409)
    snapshot = await _exception_snapshot(session, batch.id)
    if {item["exception_id"] for item in snapshot} != set(draft.unresolved_issue_ids):
        raise AppError("invalid_workflow_report", "Workflow issues differ from backend exceptions", 422)
    refs = []
    invoice_ids = {"invoice-" + file_id: record_id for file_id, record_id in
                   (await session.execute(select(UploadedFile.id, InvoiceRecord.id).join(
                       InvoiceRecord, InvoiceRecord.source_file_id == UploadedFile.id).where(
                       InvoiceRecord.workflow_task_id == task_id))).all()}
    for note in draft.narrative.evidence_notes:
        refs.append(invoice_ids.get(note.evidence_ref, note.evidence_ref))
    await _validate_evidence_references(session, task.order_id, batch.id, refs)
    version = await delivery_repo.next_report_version(session, task.order_id)
    content = "\n".join([draft.narrative.summary, *draft.narrative.next_steps,
                         *(note.explanation for note in draft.narrative.evidence_notes)])
    report = ReportVersion(
        order_id=task.order_id, version=version, status="draft", source_task_id=None,
        workflow_task_id=task_id, workflow_report_version=draft.report_version,
        reconciliation_batch_id=batch.id, report_content=content,
        financial_summary={
            "income_total_cents": batch.income_total_cents,
            "expense_total_cents": batch.expense_total_cents,
            "net_cash_change_cents": batch.net_cash_change_cents,
        },
        reconciliation_summary={
            "matched_count": batch.matched_count, "unmatched_count": batch.unmatched_count,
            "exception_count": batch.exception_count,
            "match_ids": [item.id for item in await reconciliation_repo.list_matches(session, batch.id)],
            "exception_ids": [item["exception_id"] for item in snapshot],
        },
        exception_snapshot=snapshot, evidence_references=list(dict.fromkeys(refs)),
        unresolved_items=[f"{item['exception_no']}: {item['exception_type']} ({item['status']})"
                          for item in snapshot if item["status"] != "resolved"],
        content_hash="",
    )
    report.content_hash = _content_hash(report)
    session.add(report)
    await session.flush()
    for previous in await delivery_repo.list_reports(session, task.order_id):
        if previous.id != report.id and previous.status in {"draft", "in_review", "approved"}:
            previous.status = "superseded"
    session.add(AuditLog(order_id=task.order_id, actor_type="agent_workflow", actor_id=task_id,
                         action="report.created", entity_type="report_version", entity_id=report.id,
                         details={"version": version, "workflow_report_version": draft.report_version}))
    await session.commit()
    return report


async def submit_workflow_review(session: AsyncSession, report_id: str) -> ReportVersion:
    report = await session.get(ReportVersion, report_id)
    if report is None or report.workflow_task_id is None or report.status != "draft":
        raise AppError("invalid_workflow_report", "Workflow report draft is required", 409)
    await _fresh(session, report)
    await order_state.begin_processing(session, report.order_id)
    await order_state.move(session, report.order_id, "awaiting_owner_review", "workflow_report_review")
    report.status = "in_review"
    session.add(AuditLog(order_id=report.order_id, actor_type="system", actor_id=report.workflow_task_id,
                         action="report.submitted_review", entity_type="report_version", entity_id=report.id))
    await session.commit()
    return report


async def approve_workflow_in_transaction(session: AsyncSession, task: AgentTask,
                                          run: AgentRun, output: dict) -> None:
    """Approve report in the same commit as the completed full workflow task."""
    report = await session.get(ReportVersion, output["report_id"])
    checkpoint = run.checkpoint_data or {}
    reply = checkpoint.get("reply") or {}
    actor_id = checkpoint.get("review_actor_id")
    if (report is None or report.workflow_task_id != task.id or report.status != "in_review"
            or reply.get("action") != "approve_delivery"
            or reply.get("request_id") != output["approval_request_id"] or not actor_id):
        raise AppError("workflow_approval_missing", "Matching owner approval is required", 409)
    reports = await delivery_repo.list_reports(session, task.order_id)
    if not reports or reports[0].id != report.id:
        raise AppError("old_report_version", "Only the latest report can be approved", 409)
    await _fresh(session, report)
    await order_state.move(session, report.order_id, "approved", "report_approved", "owner", actor_id)
    report.status = "approved"
    report.approved_at = utc_now()
    report.approved_by = actor_id
    session.add(ReportReviewAction(report_id=report.id, report_version=report.version,
                                   action="approved", actor_id=actor_id,
                                   content_hash=report.content_hash))
    _audit(session, report, Principal(user_id=actor_id, role="owner"),
           "report.approved", {"content_hash": report.content_hash})


async def _get(session: AsyncSession, report_id: str, principal: Principal) -> ReportVersion:
    report = await session.get(ReportVersion, report_id)
    if report is None:
        raise AppError("not_found", "Report not found", 404)
    await order_for_user(session, report.order_id, principal)
    if principal.role != "owner" and report.published_at is None:
        raise AppError("not_found", "Report not found", 404)
    return report


async def get_report(session: AsyncSession, report_id: str, principal: Principal) -> ReportVersion:
    return await _get(session, report_id, principal)


async def list_reports(session: AsyncSession, order_id: str, principal: Principal) -> list[ReportVersion]:
    await order_for_user(session, order_id, principal)
    reports = await delivery_repo.list_reports(session, order_id)
    return reports if principal.role == "owner" else [item for item in reports if item.published_at is not None]


async def _fresh(session: AsyncSession, report: ReportVersion) -> None:
    if _content_hash(report) != report.content_hash:
        raise AppError("report_content_changed", "Report content changed; create a new version", 409)
    latest = await reconciliation_repo.latest_batch(session, report.order_id)
    if latest is None or latest.id != report.reconciliation_batch_id:
        raise AppError("stale_report", "A newer reconciliation batch requires a new report version", 409)
    current = await _exception_snapshot(session, latest.id)
    if current != report.exception_snapshot:
        raise AppError("stale_report", "Exception changes require a new report version", 409)
    for item in current:
        if item["status"] != "resolved" and not any(item["exception_no"] in note for note in report.unresolved_items):
            raise AppError("unresolved_exception_undisclosed", "Unresolved exception must be disclosed", 409)


async def _owner_report(session: AsyncSession, report_id: str, principal: Principal) -> ReportVersion:
    assert_owner(principal)
    report = await _get(session, report_id, principal)
    reports = await delivery_repo.list_reports(session, report.order_id)
    if reports[0].id != report.id:
        raise AppError("old_report_version", "Only the latest report version can be reviewed or published", 409)
    return report


def _audit(session: AsyncSession, report: ReportVersion, principal: Principal, action: str,
           details: dict | None = None) -> None:
    session.add(AuditLog(order_id=report.order_id, actor_type="owner", actor_id=principal.user_id,
                         action=action, entity_type="report_version", entity_id=report.id, details=details))
    session.add(WorkflowEvent(order_id=report.order_id, event_type=action,
                              payload={"report_id": report.id, "version": report.version}))


async def submit_review(session: AsyncSession, report_id: str, principal: Principal) -> ReportVersion:
    report = await _owner_report(session, report_id, principal)
    if report.status != "draft":
        raise AppError("invalid_report_transition", "Only a draft can enter review", 409)
    await _fresh(session, report)
    await order_state.begin_processing(session, report.order_id)
    await order_state.move(session, report.order_id, "awaiting_owner_review", "report_submitted_review",
                           "owner", principal.user_id)
    report.status = "in_review"
    _audit(session, report, principal, "report.submitted_review")
    await session.commit()
    return report


async def approve(session: AsyncSession, report_id: str, principal: Principal, reason: str | None = None) -> ReportVersion:
    report = await _owner_report(session, report_id, principal)
    if report.workflow_task_id is not None:
        workflow_task = await session.get(AgentTask, report.workflow_task_id)
        if workflow_task is None or workflow_task.status != "succeeded":
            raise AppError("workflow_approval_pending", "Workflow approval must complete first", 409)
    if report.status != "in_review":
        raise AppError("invalid_report_transition", "Only an in-review report can be approved", 409)
    await _fresh(session, report)
    await order_state.move(session, report.order_id, "approved", "report_approved", "owner", principal.user_id)
    report.status = "approved"
    report.approved_at = utc_now()
    report.approved_by = principal.user_id
    session.add(ReportReviewAction(report_id=report.id, report_version=report.version,
                                   action="approved", actor_id=principal.user_id,
                                   reason=reason, content_hash=report.content_hash))
    _audit(session, report, principal, "report.approved", {"content_hash": report.content_hash})
    await session.commit()
    return report


async def reject(session: AsyncSession, report_id: str, principal: Principal, reason: str,
                 *, from_workflow: bool = False, commit: bool = True) -> ReportVersion:
    report = await _owner_report(session, report_id, principal)
    if report.workflow_task_id is not None and not from_workflow:
        raise AppError("workflow_reply_required", "Use the workflow review endpoint", 409)
    if report.status != "in_review":
        raise AppError("invalid_report_transition", "Only an in-review report can be rejected", 409)
    if not reason.strip():
        raise AppError("reason_required", "Rejection reason is required", 422)
    await order_state.move(session, report.order_id, "processing", "report_rejected", "owner", principal.user_id)
    report.status = "draft"
    session.add(ReportReviewAction(report_id=report.id, report_version=report.version,
                                   action="rejected", actor_id=principal.user_id,
                                   reason=reason.strip(), content_hash=report.content_hash))
    _audit(session, report, principal, "report.rejected", {"reason": reason.strip()})
    if commit:
        await session.commit()
    return report


async def publish(session: AsyncSession, report_id: str, principal: Principal) -> ReportVersion:
    report = await _owner_report(session, report_id, principal)
    if report.status != "approved":
        raise AppError("invalid_report_transition", "Only an approved report can be published", 409)
    await _fresh(session, report)
    approval = await delivery_repo.approval_for_report(session, report.id)
    if approval is None or approval.report_version != report.version or approval.content_hash != report.content_hash:
        raise AppError("approval_missing", "This report version has no matching approval", 409)
    for previous in await delivery_repo.list_reports(session, report.order_id):
        if previous.id != report.id and previous.status == "published":
            previous.status = "superseded"
    report.status = "published"
    report.published_at = utc_now()
    await session.flush()
    await order_state.deliver_published_report(session, report.id, principal.user_id)
    _audit(session, report, principal, "report.published")
    await session.commit()
    return report


def printable_html(report: ReportVersion) -> str:
    title = f"LedgerCrew 月度报告 v{report.version}"
    lines = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
             f"<title>{html.escape(title)}</title>",
             "<style>body{font-family:sans-serif;max-width:900px;margin:2rem auto;line-height:1.6}"
             "table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:.4rem}"
             "pre{white-space:pre-wrap}@media print{body{margin:0}}</style></head><body>",
             f"<h1>{html.escape(title)}</h1>",
             f"<p>订单：{html.escape(report.order_id)} · 版本：{report.version}</p>",
             "<h2>资金收支（整数分）</h2><ul>"]
    for key, label in (("income_total_cents", "收入"), ("expense_total_cents", "支出"),
                       ("net_cash_change_cents", "净资金变动")):
        lines.append(f"<li>{label}：{report.financial_summary[key]}</li>")
    lines.extend(["</ul><p>净资金变动不等于会计利润或应税所得。</p>",
                  "<h2>报告正文</h2>", f"<pre>{html.escape(report.report_content)}</pre>",
                  "<h2>异常披露</h2><table><tr><th>编号</th><th>类型</th><th>状态</th><th>金额（分）</th></tr>"])
    for item in report.exception_snapshot:
        lines.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            item["exception_no"], item["exception_type"], item["status"],
            item["related_amount_cents"] if item["related_amount_cents"] is not None else "")) + "</tr>")
    lines.append("</table><h2>证据引用</h2><ul>")
    lines.extend(f"<li>{html.escape(reference)}</li>" for reference in report.evidence_references)
    lines.append("</ul><h2>未解决事项</h2><ul>")
    lines.extend(f"<li>{html.escape(note)}</li>" for note in report.unresolved_items)
    lines.append("</ul></body></html>")
    return "".join(lines)
