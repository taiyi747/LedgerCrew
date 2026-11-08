import hashlib
import html
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import Principal, assert_owner
from app.db.types import utc_now
from app.integrations.agents.contracts import ReportDraftInput, ReportDraftOutput
from app.models import (AgentTask, AuditLog, BankTransaction, ExceptionSupplement, InvoiceRecord, Order,
                        ReportReviewAction, ReportVersion, ReconciliationMatch, UploadedFile, WorkflowEvent)
from app.repositories import delivery as delivery_repo
from app.repositories import reconciliation as reconciliation_repo
from app.services.access import order_for_user

# 交付文档是给客户看的：类型与状态一律人话，金额以元呈现。
EXCEPTION_TYPE_LABELS = {
    "DUPLICATE_INVOICE": "重复发票",
    "INVOICE_FIELD_MISSING": "票据字段缺失",
    "COUNTERPARTY_OR_DATE_CONFLICT": "交易方或日期不一致",
    "AMOUNT_MISMATCH": "金额不一致",
    "MULTIPLE_CANDIDATES": "多笔疑似对应",
    "MISSING_TRANSACTION": "流水缺少对应记录",
    "MISSING_INVOICE": "缺少票据",
}
EXCEPTION_STATUS_LABELS = {
    "open": "待处理",
    "waiting_customer": "待客户补充",
    "waiting_owner": "待老板决定",
    "resolved": "已处理",
    "accepted_unresolved": "保留未解决",
}


def money(cents: int | None) -> str:
    return "—" if cents is None else f"¥{cents / 100:,.2f}"


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
    if task.source_revision is not None and task.source_revision != (await session.get(Order, task.order_id)).input_revision:
        raise AppError("stale_report_source", "报告模型任务使用的输入版本已经变化。", 409)
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
    required_disclosures = [
        f"{item['exception_no']}（{EXCEPTION_TYPE_LABELS.get(item['exception_type'], item['exception_type'])}）"
        f"· {EXCEPTION_STATUS_LABELS.get(item['status'], item['status'])}"
        for item in snapshot if item["status"] != "resolved"
    ]
    unresolved = list(dict.fromkeys(output.unresolved_items + required_disclosures))
    evidence_references = list(dict.fromkeys(
        output.evidence_references + source.reconciliation_summary.match_ids +
        source.reconciliation_summary.exception_ids))
    report = ReportVersion(
        order_id=task.order_id, version=next_version, status="draft", source_task_id=task.id,
        source_revision=(await session.get(Order, task.order_id)).input_revision,
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
    order = await session.get(Order, report.order_id)
    from app.live.service import current_run
    live = await current_run(session, report.order_id)
    if live and await session.scalar(select(ReportReviewAction.id).where(
        ReportReviewAction.report_id == report.id, ReportReviewAction.action == "rejected")):
        raise AppError("rejected_report", "该报告已退回，需总管安排生成新版本。", 409)
    if report.source_revision is None or report.source_revision != order.input_revision:
        raise AppError("stale_report", "材料或人工决定已变化，需要生成新报告。", 409)
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
    report.status = "in_review"
    _audit(session, report, principal, "report.submitted_review")
    await session.commit()
    return report


async def approve(session: AsyncSession, report_id: str, principal: Principal, reason: str | None = None) -> ReportVersion:
    report = await _owner_report(session, report_id, principal)
    if report.status != "in_review":
        raise AppError("invalid_report_transition", "Only an in-review report can be approved", 409)
    await _fresh(session, report)
    report.status = "approved"
    (await session.get(Order, report.order_id)).status = "approved"
    report.approved_at = utc_now()
    report.approved_by = principal.user_id
    session.add(ReportReviewAction(report_id=report.id, report_version=report.version,
                                   action="approved", actor_id=principal.user_id,
                                   reason=reason, content_hash=report.content_hash))
    _audit(session, report, principal, "report.approved", {"content_hash": report.content_hash})
    await session.commit()
    return report


async def reject(session: AsyncSession, report_id: str, principal: Principal, reason: str) -> ReportVersion:
    report = await _owner_report(session, report_id, principal)
    if report.status != "in_review":
        raise AppError("invalid_report_transition", "Only an in-review report can be rejected", 409)
    if not reason.strip():
        raise AppError("reason_required", "Rejection reason is required", 422)
    report.status = "draft"
    session.add(ReportReviewAction(report_id=report.id, report_version=report.version,
                                   action="rejected", actor_id=principal.user_id,
                                   reason=reason.strip(), content_hash=report.content_hash))
    _audit(session, report, principal, "report.rejected", {"reason": reason.strip()})
    from app.live.service import wake_supervisor
    await wake_supervisor(session, report.order_id)
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
    (await session.get(Order, report.order_id)).status = "delivered"
    report.published_at = utc_now()
    _audit(session, report, principal, "report.published")
    from app.live.service import wake_supervisor
    await wake_supervisor(session, report.order_id)
    await session.commit()
    return report


def _report_model(report: ReportVersion, studio_name: str | None, period: str | None) -> dict:
    """HTML 与 Word 共用的展示模型：全部人话，金额以元呈现。"""
    info = " · ".join(
        part for part in (
            studio_name,
            f"{period} 账期" if period else None,
            f"报告版本 v{report.version}",
            f"生成于 {report.created_at:%Y-%m-%d}" if report.created_at else None,
        ) if part
    )
    return {
        "title": "账目核对报告",
        "info": info,
        "summary": [
            ("收入", money(report.financial_summary.get("income_total_cents"))),
            ("支出", money(report.financial_summary.get("expense_total_cents"))),
            ("净资金变动", money(report.financial_summary.get("net_cash_change_cents"))),
        ],
        "summary_note": "净资金变动不等于会计利润或应税所得。",
        "content": [line for line in (report.report_content or "").splitlines() if line.strip()],
        "exceptions": [
            [
                item.get("exception_no", ""),
                EXCEPTION_TYPE_LABELS.get(item.get("exception_type"), item.get("exception_type", "")),
                money(item.get("related_amount_cents")),
                money(item.get("difference_cents")),
                EXCEPTION_STATUS_LABELS.get(item.get("status"), item.get("status", "")),
            ]
            for item in (report.exception_snapshot or [])
        ],
        "exception_head": ["异常编号", "事项类型", "关联金额", "待核实差额", "处理状态"],
        "unresolved": list(report.unresolved_items or []),
        "evidence_note": f"本报告依据 {len(report.evidence_references or [])} 项对账与材料记录生成，可在平台逐项追溯。",
        "disclaimer": "本报告仅用于经营核对，不构成审计、鉴证或税务意见。",
    }


def printable_html(report: ReportVersion, *, studio_name: str | None = None, period: str | None = None) -> str:
    model = _report_model(report, studio_name, period)
    esc = html.escape
    lines = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        f"<title>小账房 · {esc(model['title'])} v{report.version}</title>",
        "<style>body{font-family:sans-serif;max-width:900px;margin:2rem auto;line-height:1.8;color:#243e4c}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.5rem .6rem;text-align:left}"
        "h1{font-size:1.6rem}h2{font-size:1.15rem;margin-top:2rem}@media print{body{margin:0}}</style></head><body>",
        f"<h1>小账房 · {esc(model['title'])}</h1>",
        f"<p>{esc(model['info'])}</p>",
        "<h2>财务摘要</h2><table><tr><th>项目</th><th>金额</th></tr>",
    ]
    for label, value in model["summary"]:
        lines.append(f"<tr><td>{esc(label)}</td><td>{esc(value)}</td></tr>")
    lines.append("</table>")
    lines.append(f"<p>{esc(model['summary_note'])}</p>")
    lines.append("<h2>核对结论</h2>")
    lines.extend(f"<p>{esc(paragraph)}</p>" for paragraph in model["content"])
    lines.append("<h2>异常披露</h2>")
    if model["exceptions"]:
        lines.append("<table><tr>" + "".join(f"<th>{esc(head)}</th>" for head in model["exception_head"]) + "</tr>")
        for row in model["exceptions"]:
            lines.append("<tr>" + "".join(f"<td>{esc(str(cell))}</td>" for cell in row) + "</tr>")
        lines.append("</table>")
    else:
        lines.append("<p>本期没有待披露的异常事项。</p>")
    lines.append("<h2>未解决事项</h2>")
    if model["unresolved"]:
        lines.append("<ul>")
        lines.extend(f"<li>{esc(note)}</li>" for note in model["unresolved"])
        lines.append("</ul>")
    else:
        lines.append("<p>无。</p>")
    lines.append(f"<h2>依据说明</h2><p>{esc(model['evidence_note'])}</p>")
    lines.append(f"<p>{esc(model['disclaimer'])}</p>")
    lines.append("</body></html>")
    return "".join(lines)
