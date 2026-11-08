"""Versioned, framework-independent Agent data contracts (v1)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator

AgentRole = Literal[
    "customer_reception", "material_review", "invoice_processing",
    "data_reconciliation", "risk_delivery",
]
AgentStatus = Literal["queued", "running", "paused", "succeeded", "failed"]
ReviewStatus = Literal["ACCEPTED", "REJECTED", "NEEDS_REUPLOAD", "NEEDS_REVIEW"]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerReceptionInput(StrictContract):
    order_id: str
    customer_message: str
    submitted_file_ids: list[str] = Field(default_factory=list)


class CustomerReceptionOutput(StrictContract):
    needs_summary: str
    material_reminders: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


class MaterialReviewInput(StrictContract):
    order_id: str
    file_id: str
    file_category: str
    mime_type: str


class MaterialReviewOutput(StrictContract):
    file_id: str
    document_type: str | None = None
    review_status: ReviewStatus
    is_invoice: bool
    readability: str | None = None
    reason: str | None = None
    confidence: float = Field(ge=0, le=1)
    next_action: str | None = None


class InvoiceExtractionInput(StrictContract):
    order_id: str
    file_id: str
    mime_type: str


class InvoiceExtractionOutput(StrictContract):
    file_id: str
    invoice_number: str | None = None
    issue_date: date | None = None
    seller: str | None = None
    buyer: str | None = None
    # Raw extracted strings. Deterministic backend code validates and converts
    # these to integer cents before creating an InvoiceRecord.
    amount: str | None = None
    tax_amount: str | None = None
    total_amount: str | None = None
    invoice_type: str | None = None
    confidence: float = Field(ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list)
    extraction_status: Literal["ready", "needs_review", "invalid"]


class FinancialSummary(StrictContract):
    income_total_cents: StrictInt = Field(ge=0)
    expense_total_cents: StrictInt = Field(ge=0)
    net_cash_change_cents: StrictInt

    @model_validator(mode="after")
    def validate_net_change(self) -> "FinancialSummary":
        if self.net_cash_change_cents != self.income_total_cents - self.expense_total_cents:
            raise ValueError("Net cash change must equal income minus expense")
        return self


class ReconciliationSummary(StrictContract):
    batch_id: str
    matched_count: StrictInt = Field(ge=0)
    unmatched_count: StrictInt = Field(ge=0)
    exception_count: StrictInt = Field(ge=0)
    match_ids: list[str] = Field(default_factory=list)
    exception_ids: list[str] = Field(default_factory=list)


class ReconciliationAgentInput(StrictContract):
    order_id: str
    financial_summary: FinancialSummary
    reconciliation_result: ReconciliationSummary
    evidence_references: list[str] = Field(default_factory=list)


class ReconciliationAgentOutput(StrictContract):
    narrative_summary: str
    observations: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)


class RiskAnalysisInput(StrictContract):
    order_id: str
    exception_id: str
    exception_type: str
    evidence: dict[str, JsonValue]
    related_amount: StrictInt | None = None  # integer cents, copied from backend ticket
    difference: StrictInt | None = None  # integer cents, copied from backend ticket


class RiskAnalysisOutput(StrictContract):
    exception_id: str
    preliminary_analysis: str
    customer_questions: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)


class ExceptionSummary(StrictContract):
    exception_id: str
    exception_type: str
    status: str
    related_amount_cents: StrictInt | None = None
    difference_cents: StrictInt | None = None
    evidence_references: list[str] = Field(default_factory=list)


class ReportDraftInput(StrictContract):
    order_id: str
    report_version: int = Field(ge=1)
    financial_summary: FinancialSummary
    reconciliation_summary: ReconciliationSummary
    exception_summary: list[ExceptionSummary] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)


class ReportDraftOutput(StrictContract):
    order_id: str
    report_version: int = Field(ge=1)
    report_content: str = Field(min_length=1)
    evidence_references: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def human_readable_delivery_text(self) -> "ReportDraftOutput":
        """交付文字面向客户：内部标识和以分计的金额一律退回重写。"""
        import re

        machine = re.compile(
            r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-|EX-[0-9A-F]{6,}|\b[a-z]+_[a-z_]+\b|\d{3,}\s*分)",
            re.IGNORECASE,
        )
        for text in (self.report_content, *self.unresolved_items):
            if machine.search(text):
                raise ValueError(
                    "报告文字不得包含内部编号、UUID、字段名或以「分」计的金额；"
                    "金额与编号由后端明细表展示，正文与未解决事项只写业务描述。"
                )
        return self


TASK_CONTRACTS: dict[str, tuple[AgentRole, type[StrictContract], type[StrictContract]]] = {
    "customer_reception": ("customer_reception", CustomerReceptionInput, CustomerReceptionOutput),
    "material_review": ("material_review", MaterialReviewInput, MaterialReviewOutput),
    "invoice_extraction": ("invoice_processing", InvoiceExtractionInput, InvoiceExtractionOutput),
    "reconciliation_summary": ("data_reconciliation", ReconciliationAgentInput, ReconciliationAgentOutput),
    "risk_analysis": ("risk_delivery", RiskAnalysisInput, RiskAnalysisOutput),
    "report_draft": ("risk_delivery", ReportDraftInput, ReportDraftOutput),
}


def contract_for(agent_role: AgentRole, task_type: str, schema_version: str) -> tuple[type[StrictContract], type[StrictContract]]:
    if schema_version != "1.0" or task_type not in TASK_CONTRACTS or TASK_CONTRACTS[task_type][0] != agent_role:
        raise ValueError("Unsupported Agent role, task type, or schema version")
    return TASK_CONTRACTS[task_type][1:]


class AgentInvocationRequest(StrictContract):
    task_id: str
    run_id: str
    order_id: str
    agent_role: AgentRole
    task_type: str
    input_schema_version: str
    idempotency_key: str = Field(min_length=1, max_length=100)
    correlation_id: str = Field(min_length=1, max_length=100)
    input_payload: dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_business_input(self) -> "AgentInvocationRequest":
        input_model, _ = contract_for(self.agent_role, self.task_type, self.input_schema_version)
        payload = input_model.model_validate(self.input_payload)
        if getattr(payload, "order_id") != self.order_id:
            raise ValueError("Payload order_id must match invocation order_id")
        return self


class AgentInvocationResponse(StrictContract):
    task_id: str
    status: AgentStatus
    output_payload: dict[str, JsonValue] | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    provider_metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_response(self) -> "AgentInvocationResponse":
        if self.started_at.tzinfo is None or (self.finished_at is not None and self.finished_at.tzinfo is None):
            raise ValueError("Agent timestamps must include a timezone")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if self.status == "succeeded" and (self.output_payload is None or self.finished_at is None or self.error):
            raise ValueError("Successful response needs output and finished_at, without error")
        if self.status == "failed" and (not self.error or self.finished_at is None):
            raise ValueError("Failed response needs error and finished_at")
        if self.status == "paused" and self.finished_at is not None:
            raise ValueError("Paused response must not have finished_at")
        return self
