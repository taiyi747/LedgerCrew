import csv
import io
import json
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import Principal
from app.models import BankTransaction, InvoiceRecord, ReconciliationBatch
from app.repositories import delivery as delivery_repo
from app.repositories import reconciliation as reconciliation_repo
from app.services.access import order_for_user

EXPORT_TYPES = {"invoices", "transactions", "matches", "exceptions"}


def _cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, (date, datetime)):
        value = value.isoformat()
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv(headers: list[str], rows: list[list[object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows([[_cell(value) for value in row] for row in rows])
    return stream.getvalue().encode("utf-8-sig")


async def export_csv(session: AsyncSession, order_id: str, export_type: str,
                     principal: Principal) -> bytes:
    await order_for_user(session, order_id, principal)
    if export_type not in EXPORT_TYPES:
        raise AppError("unsupported_export", "Unsupported CSV export type", 404)
    reports = await delivery_repo.list_reports(session, order_id)
    published = next((item for item in reports if item.published_at is not None), None)
    if principal.role != "owner" and published is None:
        raise AppError("not_found", "No published report exists for this order", 404)
    batch = (await session.get(ReconciliationBatch, published.reconciliation_batch_id)
             if principal.role != "owner" else await reconciliation_repo.latest_batch(session, order_id))
    cutoff = published.created_at if principal.role != "owner" else datetime.now(UTC)
    if export_type == "invoices":
        records = (await session.scalars(select(InvoiceRecord).where(
            InvoiceRecord.order_id == order_id, InvoiceRecord.created_at <= cutoff)
            .order_by(InvoiceRecord.created_at, InvoiceRecord.id))).all()
        return _csv(["id", "source_file_id", "invoice_number", "issue_date", "seller", "buyer",
                     "amount_cents", "tax_cents", "total_amount_cents", "extraction_status", "created_at"],
                    [[item.id, item.source_file_id, item.invoice_number, item.issue_date, item.seller, item.buyer,
                      item.amount_cents, item.tax_cents, item.total_amount_cents, item.extraction_status,
                      item.created_at] for item in records])
    if export_type == "transactions":
        records = (await session.scalars(select(BankTransaction).where(
            BankTransaction.order_id == order_id, BankTransaction.created_at <= cutoff)
            .order_by(BankTransaction.transaction_date, BankTransaction.id))).all()
        return _csv(["id", "statement_import_id", "row_number", "external_id", "transaction_date", "counterparty",
                     "normalized_counterparty", "direction", "amount_cents", "description", "raw_row_json"],
                    [[item.id, item.statement_import_id, item.row_number, item.external_id, item.transaction_date,
                      item.counterparty, item.normalized_counterparty, item.direction, item.amount_cents,
                      item.description, item.raw_row_json] for item in records])
    if export_type == "matches":
        records = await reconciliation_repo.list_matches(session, batch.id) if batch else []
        return _csv(["id", "invoice_id", "transaction_id", "match_status", "difference_cents", "match_rule", "evidence_json"],
                    [[item.id, item.invoice_id, item.transaction_id, item.match_status, item.difference_cents,
                      item.match_rule, item.evidence_json] for item in records])
    if principal.role != "owner":
        return _csv(["id", "exception_no", "exception_type", "invoice_id", "transaction_id", "related_amount_cents",
                     "difference_cents", "status", "business_classification", "evidence_json"],
                    [[item["exception_id"], item["exception_no"], item["exception_type"],
                      item["invoice_id"], item["transaction_id"],
                      item["related_amount_cents"], item["difference_cents"], item["status"],
                      item["business_classification"], item["evidence"]]
                     for item in published.exception_snapshot])
    records = await reconciliation_repo.list_tickets(session, batch.id) if batch else []
    return _csv(["id", "exception_no", "exception_type", "invoice_id", "transaction_id", "related_amount_cents",
                 "difference_cents", "status", "business_classification", "evidence_json"],
                [[item.id, item.exception_no, item.exception_type, item.invoice_id, item.transaction_id,
                  item.related_amount_cents, item.difference_cents, item.status, item.business_classification,
                  item.evidence_json] for item in records])
