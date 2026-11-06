"""Local fixture backend ONLY. Replace it with real backend services for customer data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import unicodedata
import uuid
from pathlib import Path

from .contracts import AgentEvent, InvoiceRecord, Issue, Match, OrderInput, ReconciliationResult, RunIdentity
from .errors import AgentError


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _normalize(text: str | None) -> str:
    return "".join(unicodedata.normalize("NFKC", text or "").casefold().split())


def reconcile_fixture(order: OrderInput, invoices: list[InvoiceRecord]) -> ReconciliationResult:
    """Reference fixture calculator, deliberately outside the production workflow."""
    matches, issues = [], []
    used_transactions: set[str] = set()
    seen: set[str] = set()
    total = 0
    for invoice in invoices:
        refs = [invoice.id, invoice.source_file_id]
        key = _normalize(invoice.invoice_number)
        if key and key in seen:
            issues.append(
                Issue(
                    id="duplicate-" + invoice.id,
                    kind="duplicate",
                    description="票据号码重复",
                    invoice_ids=[invoice.id],
                    evidence_refs=refs,
                )
            )
            continue
        if key:
            seen.add(key)
        if invoice.needs_review:
            issues.append(
                Issue(
                    id="uncertain-" + invoice.id,
                    kind="uncertain_fields",
                    description="票据字段待确认",
                    invoice_ids=[invoice.id],
                    evidence_refs=refs,
                )
            )
            continue
        total += invoice.amount_minor or 0
        candidates = [
            t
            for t in order.transactions
            if t.id not in used_transactions
            and _normalize(t.counterparty) == _normalize(invoice.counterparty)
            and t.direction == invoice.direction
            and invoice.date is not None
            and abs((t.date - invoice.date).days) <= 3
        ]
        exact = [t for t in candidates if t.amount_minor == invoice.amount_minor]
        if len(exact) == 1:
            transaction = exact[0]
            matches.append(
                Match(
                    invoice_id=invoice.id,
                    transaction_id=transaction.id,
                    amount_minor=transaction.amount_minor,
                    evidence_refs=[*refs, transaction.id, transaction.source_file_id],
                )
            )
            used_transactions.add(transaction.id)
        elif len(exact) > 1 or len(candidates) > 1:
            issues.append(
                Issue(
                    id="ambiguous-" + invoice.id,
                    kind="ambiguous",
                    description="存在多个候选付款",
                    invoice_ids=[invoice.id],
                    transaction_ids=[t.id for t in candidates],
                    evidence_refs=refs + [t.id for t in candidates],
                )
            )
        elif candidates:
            transaction = candidates[0]
            used_transactions.add(transaction.id)
            issues.append(
                Issue(
                    id="difference-" + invoice.id,
                    kind="amount_mismatch",
                    description="票据与付款金额不同，原因待核实",
                    invoice_ids=[invoice.id],
                    transaction_ids=[transaction.id],
                    difference_minor=transaction.amount_minor - (invoice.amount_minor or 0),
                    evidence_refs=[*refs, transaction.id, transaction.source_file_id],
                )
            )
        else:
            issues.append(
                Issue(
                    id="missing-payment-" + invoice.id,
                    kind="missing_transaction",
                    description="未找到对应付款",
                    invoice_ids=[invoice.id],
                    evidence_refs=refs,
                )
            )
    for transaction in order.transactions:
        if transaction.id not in used_transactions:
            issues.append(
                Issue(
                    id="missing-invoice-" + transaction.id,
                    kind="missing_invoice",
                    description="流水缺少唯一对应票据",
                    transaction_ids=[transaction.id],
                    evidence_refs=[transaction.id, transaction.source_file_id],
                )
            )
    return ReconciliationResult(
        identity=order.identity,
        matches=matches,
        issues=issues,
        invoice_total_minor=total,
        transaction_total_minor=sum(t.amount_minor for t in order.transactions),
    )


class FixtureBackend:
    """Filesystem adapter for the repository's synthetic fixtures, not customer uploads.

    The owning backend must supply authorization, DB transactions, execution leases,
    input revision checks and its own reconciliation implementation.
    """

    def __init__(self, data_dir: Path, fixtures_dir: Path):
        self.root = data_dir.resolve()
        self.fixtures = fixtures_dir.resolve()
        self._lock = asyncio.Lock()
        self.manifest = json.loads((self.fixtures / "manifest.json").read_text(encoding="utf-8"))

    def _run_dir(self, identity: RunIdentity) -> Path:
        return self.root / identity.order_id / identity.run_id

    def put_order(self, order: OrderInput) -> None:
        _write(self.root / order.identity.order_id / "order.json", order.model_dump(mode="json"))

    async def load_order(self, order_id: str) -> OrderInput:
        if not order_id or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in order_id
        ):
            raise AgentError("不合法的订单标识。")
        return OrderInput.model_validate_json(
            (self.root / order_id / "order.json").read_text(encoding="utf-8")
        )

    async def read_invoice(self, order_id: str, file_id: str) -> bytes:
        order = await self.load_order(order_id)
        file = next((f for f in order.files if f.id == file_id), None)
        if file is None or file.name not in self.manifest:
            raise AgentError("本地适配器只允许读取已登记的合成票据。")
        path = self.fixtures / file.name
        if path.resolve().parent != self.fixtures:
            raise AgentError("不合法的样例路径。")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.manifest[file.name]:
            raise AgentError("合成票据校验不一致。")
        return data

    async def reconcile(self, order: OrderInput, invoices: list[InvoiceRecord]) -> ReconciliationResult:
        for file in order.files:
            await self.read_invoice(order.identity.order_id, file.id)
        return reconcile_fixture(order, invoices)

    async def save_artifact(
        self, identity: RunIdentity, kind: str, payload: dict, idempotency_key: str
    ) -> str:
        artifact_id = hashlib.sha256(idempotency_key.encode()).hexdigest()
        run_dir = self._run_dir(identity)
        record = {"identity": identity.model_dump(mode="json"), "kind": kind, "payload": payload}
        async with self._lock:
            history = run_dir / "artifacts" / (artifact_id + ".json")
            if history.exists() and json.loads(history.read_text(encoding="utf-8")) != record:
                raise AgentError("相同幂等标识对应不同成果。")
            _write(history, record)
            _write(run_dir / "latest" / (hashlib.sha256(kind.encode()).hexdigest() + ".json"), record)
        return artifact_id

    async def load_artifact(self, identity: RunIdentity, kind: str) -> dict | None:
        path = self._run_dir(identity) / "latest" / (hashlib.sha256(kind.encode()).hexdigest() + ".json")
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))["payload"]

    async def emit_event(self, event: AgentEvent) -> None:
        path = self._run_dir(event.identity) / "events" / (event.event_id + ".json")
        if not path.exists():
            _write(path, event.model_dump(mode="json"))

    def events(self, identity: RunIdentity) -> list[dict]:
        return sorted(
            [
                json.loads(p.read_text(encoding="utf-8"))
                for p in (self._run_dir(identity) / "events").glob("*.json")
            ],
            key=lambda e: e["created_at"],
        )
