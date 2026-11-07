"""Production database and file adapter for the existing MAF workflow graph."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.contracts import (
    AgentEvent,
    FileRef,
    Issue,
    Match,
    OrderInput,
    ReconciliationResult,
    RunIdentity,
    Transaction,
)
from app.agents.contracts import (
    InvoiceRecord as WorkflowInvoice,
)
from app.agents.errors import StaleReviewError
from app.core.security import Principal
from app.integrations.agents.mimo_gateway import TaskModelArtifacts
from app.models import (
    AgentModelArtifact,
    AgentTask,
    BankTransaction,
    InvoiceRecord,
    Order,
    StatementImport,
    Studio,
    UploadedFile,
    WorkflowEvent,
)
from app.repositories import reconciliation as reconciliation_repo
from app.services import reconciliation_service
from app.storage.base import Storage

_ISSUE_TYPES = {
    "AMOUNT_MISMATCH": "amount_mismatch",
    "DUPLICATE_INVOICE": "duplicate",
    "DUPLICATE_TRANSACTION": "duplicate",
    "MISSING_INVOICE": "missing_invoice",
    "MISSING_TRANSACTION": "missing_transaction",
    "MULTIPLE_CANDIDATES": "ambiguous",
    "INVOICE_FIELD_MISSING": "uncertain_fields",
    "COUNTERPARTY_OR_DATE_CONFLICT": "ambiguous",
}


def _fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode()).hexdigest()


async def order_snapshot(db: AsyncSession, order_id: str) -> dict[str, Any]:
    order = await db.get(Order, order_id)
    if order is None:
        raise ValueError("Order does not exist")
    if (order.period_start.year, order.period_start.month) != (order.period_end.year, order.period_end.month):
        raise ValueError("Full workflow requires an order within one calendar month")
    studio = await db.get(Studio, order.studio_id)
    files = (await db.scalars(select(UploadedFile).where(
        UploadedFile.order_id == order_id, UploadedFile.file_category == "invoice_image",
        UploadedFile.validation_status == "valid").order_by(UploadedFile.created_at, UploadedFile.id))).all()
    if not 1 <= len(files) <= 20:
        raise ValueError("Full workflow requires 1 to 20 validated invoice images")
    transactions = (await db.scalars(select(BankTransaction).where(
        BankTransaction.order_id == order_id).order_by(
            BankTransaction.transaction_date, BankTransaction.id))).all()
    if len(transactions) > 200:
        raise ValueError("Full workflow supports at most 200 transactions")
    imports = {item.id: item.uploaded_file_id for item in (await db.scalars(select(StatementImport).where(
        StatementImport.order_id == order_id))).all()}
    return {
        "order_id": order_id, "company_name": studio.name,
        "period": f"{order.period_start.year}-{order.period_start.month:02d}",
        "files": [{"id": f.id, "name": f.original_filename, "mime_type": f.mime_type,
                   "sha256": f.sha256} for f in files],
        "transactions": [{
            "id": t.id, "date": t.transaction_date.isoformat(), "counterparty": t.counterparty,
            "amount_minor": t.amount_cents, "direction": t.direction.lower(),
            "source_file_id": imports[t.statement_import_id], "source_row": t.row_number,
            "remark": t.description or "",
        } for t in transactions],
    }


class DatabaseWorkflowBackend:
    """A task-scoped adapter; customer data never enters application logs."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], storage: Storage,
                 task_id: str) -> None:
        self.sessions = sessions
        self.storage = storage
        self.task_id = task_id
        self.model_artifacts = TaskModelArtifacts(sessions, task_id)

    async def load_order(self, order_id: str) -> OrderInput:
        async with self.sessions() as db:
            task = await db.get(AgentTask, self.task_id)
            if task is None or task.order_id != order_id or task.task_type != "full_workflow":
                raise ValueError("Workflow task identity differs")
            snapshot = await order_snapshot(db, order_id)
            if _fingerprint(snapshot) != task.input_data["input_fingerprint"]:
                raise StaleReviewError("订单材料或流水已改变，需要创建新工作流。")
            identity = RunIdentity(order_id=order_id, run_id=task.run_id,
                                   revision=task.input_data["revision"])
            return OrderInput(
                identity=identity, company_name=snapshot["company_name"],
                period=snapshot["period"],
                files=[FileRef.model_validate(f) for f in (
                    {k: f[k] for k in ("id", "name", "mime_type")} for f in snapshot["files"])],
                transactions=[Transaction.model_validate(t) for t in snapshot["transactions"]],
            )

    async def read_invoice(self, order_id: str, file_id: str) -> bytes:
        async with self.sessions() as db:
            source = await db.get(UploadedFile, file_id)
            if (source is None or source.order_id != order_id or
                    source.file_category != "invoice_image" or source.validation_status != "valid" or
                    source.mime_type not in {"image/png", "image/jpeg"}):
                raise ValueError("Workflow invoice source is invalid")
            data = self.storage.read(source.storage_key)
            if hashlib.sha256(data).hexdigest() != source.sha256:
                raise ValueError("Workflow invoice checksum mismatch")
            return data

    async def reconcile(self, order: OrderInput,
                        invoices: list[WorkflowInvoice]) -> ReconciliationResult:
        async with self.sessions() as db:
            existing = (await db.scalars(select(InvoiceRecord).where(
                InvoiceRecord.workflow_task_id == self.task_id))).all()
            by_file = {record.source_file_id: record for record in existing}
            if len({invoice.source_file_id for invoice in invoices}) != len(invoices):
                raise ValueError("Duplicate workflow invoice source")
            for invoice in invoices:
                if invoice.source_file_id in by_file:
                    continue
                source = await db.get(UploadedFile, invoice.source_file_id)
                if source is None or source.order_id != order.identity.order_id:
                    raise ValueError("Workflow invoice belongs to another order")
                studio_name = order.company_name
                record = InvoiceRecord(
                    order_id=order.identity.order_id, workflow_task_id=self.task_id,
                    source_file_id=invoice.source_file_id, invoice_number=invoice.invoice_number,
                    issue_date=invoice.date,
                    seller=invoice.counterparty if invoice.direction == "out" else studio_name,
                    buyer=studio_name if invoice.direction == "out" else invoice.counterparty,
                    amount_cents=invoice.amount_minor,
                    total_amount_cents=invoice.amount_minor if invoice.amount_minor and invoice.amount_minor > 0 else None,
                    tax_cents=None, extraction_status="needs_review" if invoice.needs_review else "ready",
                    confidence_data={"workflow_task_id": self.task_id,
                                     "uncertain_fields": invoice.uncertain_fields},
                )
                db.add(record)
            await db.commit()
            batch = await reconciliation_service.run(
                db, order.identity.order_id, Principal(user_id="workflow-system", role="owner"),
                workflow_task_id=self.task_id)
            db_invoices = (await db.scalars(select(InvoiceRecord).where(
                InvoiceRecord.workflow_task_id == self.task_id))).all()
            source_map = {item.id: "invoice-" + item.source_file_id for item in db_invoices}
            source_file_map = {item.id: item.source_file_id for item in db_invoices}
            transactions = {t.id: t for t in order.transactions}
            matches = await reconciliation_repo.list_matches(db, batch.id)
            tickets = await reconciliation_repo.list_tickets(db, batch.id)
            output_matches = [Match(
                invoice_id=source_map[item.invoice_id], transaction_id=item.transaction_id,
                amount_minor=transactions[item.transaction_id].amount_minor,
                evidence_refs=[source_map[item.invoice_id], source_file_map[item.invoice_id],
                               item.transaction_id, transactions[item.transaction_id].source_file_id])
                for item in matches]
            output_issues = []
            for item in tickets:
                invoice_ids = [source_map[item.invoice_id]] if item.invoice_id else []
                transaction_ids = [item.transaction_id] if item.transaction_id else []
                refs = [*invoice_ids, *transaction_ids]
                if item.invoice_id:
                    refs.append(source_file_map[item.invoice_id])
                if item.transaction_id:
                    refs.append(transactions[item.transaction_id].source_file_id)
                if not refs:
                    raise ValueError("Reconciliation ticket lacks evidence")
                output_issues.append(Issue(
                    id=item.id, kind=_ISSUE_TYPES[item.exception_type],
                    description=item.exception_type, invoice_ids=invoice_ids,
                    transaction_ids=transaction_ids, difference_minor=item.difference_cents,
                    evidence_refs=refs))
            return ReconciliationResult(
                identity=order.identity, matches=output_matches, issues=output_issues,
                invoice_total_minor=sum(i.amount_minor or 0 for i in invoices),
                transaction_total_minor=sum(t.amount_minor for t in order.transactions))

    async def reserve_request(self, limit: int) -> str:
        return await self.model_artifacts.reserve_request(limit)

    async def settle_request(self, identity: RunIdentity, reservation_id: str, status: str,
                             http_status: int | None, usage: dict[str, int] | None) -> None:
        await self.model_artifacts.settle_request(identity, reservation_id, status, http_status, usage)

    async def save_artifact(self, identity: RunIdentity, kind: str,
                            payload: dict[str, Any], idempotency_key: str) -> str:
        if kind in {"usage", "wire_request", "model_usage"}:
            return await self.model_artifacts.save_artifact(identity, kind, payload, idempotency_key)
        stored_kind = "wf:" + hashlib.sha256(kind.encode()).hexdigest()[:32]
        wrapped = {"kind": kind, "identity": identity.model_dump(mode="json"), "value": payload}
        return await self.model_artifacts.save_artifact(identity, stored_kind, wrapped, idempotency_key)

    async def load_artifact(self, identity: RunIdentity, kind: str) -> dict[str, Any] | None:
        if kind in {"usage", "wire_request", "model_usage"}:
            return await self.model_artifacts.load_artifact(identity, kind)
        stored_kind = "wf:" + hashlib.sha256(kind.encode()).hexdigest()[:32]
        wrapped = await self.model_artifacts.load_artifact(identity, stored_kind)
        if wrapped is None:
            return None
        if wrapped["kind"] != kind or wrapped["identity"]["run_id"] != identity.run_id:
            raise ValueError("Workflow artifact identity mismatch")
        return wrapped["value"]

    async def emit_event(self, event: AgentEvent) -> None:
        key = "event:" + event.event_id
        async with self.sessions() as db:
            existing = await db.scalar(select(AgentModelArtifact.id).where(
                AgentModelArtifact.task_id == self.task_id,
                AgentModelArtifact.idempotency_key == key))
            if existing is not None:
                return
            db.add(AgentModelArtifact(
                task_id=self.task_id, kind="wf:event", idempotency_key=key,
                payload=event.model_dump(mode="json")))
            db.add(WorkflowEvent(
                order_id=event.identity.order_id, run_id=event.identity.run_id,
                task_id=self.task_id, event_type=f"agent.workflow.{event.type}",
                payload={"agent": event.agent, "event_id": event.event_id,
                         "evidence_count": len(event.evidence_refs)}))
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()  # The event was already written atomically elsewhere.


def snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    return _fingerprint(snapshot)
