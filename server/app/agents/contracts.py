"""The AI/backend boundary. Monetary business decisions belong to the backend."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DataModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RunIdentity(DataModel):
    order_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    revision: int = Field(ge=1)


class FileRef(DataModel):
    id: str
    name: str
    mime_type: Literal["image/png", "image/jpeg"]


class Transaction(DataModel):
    id: str
    date: date
    counterparty: str
    amount_minor: int = Field(ge=0)
    direction: Literal["in", "out"] = "out"
    source_file_id: str
    source_row: int = Field(ge=1)
    remark: str = ""


class OrderInput(DataModel):
    identity: RunIdentity
    company_name: str
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    files: list[FileRef] = Field(min_length=1, max_length=20)
    transactions: list[Transaction] = Field(max_length=200)
    customer_notes: list[str] = Field(default_factory=list)


class InvoiceExtraction(DataModel):
    """Raw model output; money is normalized by code, never float arithmetic."""

    invoice_number: str | None
    date: date | None
    counterparty: str | None
    amount_text: str | None
    currency: Literal["CNY"] = "CNY"
    direction: Literal["in", "out"] = "out"
    uncertain_fields: list[str] = Field(default_factory=list)
    evidence_text: str


class InvoiceRecord(InvoiceExtraction):
    identity: RunIdentity
    id: str
    source_file_id: str
    amount_minor: int | None = Field(default=None, ge=0)
    needs_review: bool = False


class Match(DataModel):
    invoice_id: str
    transaction_id: str
    amount_minor: int = Field(ge=0)
    evidence_refs: list[str]


class Issue(DataModel):
    id: str
    kind: Literal[
        "amount_mismatch",
        "duplicate",
        "missing_invoice",
        "missing_transaction",
        "ambiguous",
        "uncertain_fields",
    ]
    description: str
    invoice_ids: list[str] = Field(default_factory=list)
    transaction_ids: list[str] = Field(default_factory=list)
    difference_minor: int | None = None
    evidence_refs: list[str]


class ReconciliationResult(DataModel):
    identity: RunIdentity
    matches: list[Match]
    issues: list[Issue]
    invoice_total_minor: int = Field(ge=0)
    transaction_total_minor: int = Field(ge=0)


ReviewAction = Literal[
    "request_info",
    "submit_information",
    "keep_flagged",
    "approve_delivery",
    "revise_report",
]


class ReviewRequest(DataModel):
    identity: RunIdentity
    request_id: str
    kind: Literal["exception", "customer", "delivery"]
    question: str
    allowed_actions: list[ReviewAction]
    evidence_refs: list[str]
    report_version: int | None = None


class HumanReply(DataModel):
    identity: RunIdentity
    request_id: str
    action: ReviewAction
    comment: str = ""
    report_version: int | None = None


class EvidenceNote(DataModel):
    evidence_ref: str
    explanation: str


class ReportNarrative(DataModel):
    summary: str
    next_steps: list[str]
    evidence_notes: list[EvidenceNote]

    @field_validator("summary", "next_steps", "evidence_notes")
    @classmethod
    def numeric_facts_are_structured(cls, value):
        texts = (
            [value]
            if isinstance(value, str)
            else [v.explanation if isinstance(v, EvidenceNote) else v for v in value]
        )
        if any(re.search(r"\d", text) for text in texts):
            raise ValueError("Report prose must omit digits; authoritative numbers are in reconciliation.")
        return value


class ReportDraft(DataModel):
    identity: RunIdentity
    report_version: int = Field(ge=1)
    narrative: ReportNarrative
    reconciliation: ReconciliationResult
    unresolved_issue_ids: list[str]
    customer_notes: list[str]


class AgentEvent(DataModel):
    identity: RunIdentity
    event_id: str
    agent: str
    type: Literal["started", "completed", "waiting", "failed", "delivery_approved"]
    message: str
    evidence_refs: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentDependencies(Protocol):
    """Adapters must serialize a logical run and make artifact/event writes idempotent."""

    async def load_order(self, order_id: str) -> OrderInput: ...

    async def read_invoice(self, order_id: str, file_id: str) -> bytes: ...

    async def reconcile(
        self,
        order: OrderInput,
        invoices: list[InvoiceRecord],
    ) -> ReconciliationResult: ...

    async def save_artifact(
        self,
        identity: RunIdentity,
        kind: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> str: ...

    async def load_artifact(
        self,
        identity: RunIdentity,
        kind: str,
    ) -> dict[str, Any] | None: ...

    async def emit_event(self, event: AgentEvent) -> None: ...


class SupervisorDecision(DataModel):
    next_action: Literal["extract"]
    explanation: str


class ReconciliationAcknowledgement(DataModel):
    summary: str


class CustomerDraft(DataModel):
    question: str = Field(pattern=r"^[^0-9]*$")
    evidence_refs: list[str]


class RunState(DataModel):
    order: OrderInput
    invoices: list[InvoiceRecord] = Field(default_factory=list)
    reconciliation: ReconciliationResult | None = None
    report: ReportDraft | None = None
    report_version: int = 0
    report_feedback: str = ""
    next_step: Literal["extract", "report"] = "extract"


class RunOutcome(DataModel):
    identity: RunIdentity
    status: Literal["delivery_approved"]
    report: ReportDraft
    approval_request_id: str
