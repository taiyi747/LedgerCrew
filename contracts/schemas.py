"""P2-0 proposed Pydantic 2 wire contracts. Design artifact, not mounted routes."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

Id = UUID
Money = StrictInt
Version = Annotated[StrictInt, Field(ge=1)]
Rate = Annotated[str, Field(pattern=r"^(0|[1-9]\d*)(\.\d+)?$")]
ScopeStatus = Literal["draft", "verified", "active", "retired"]
ImportStatus = Literal["pending", "parsed", "needs_mapping", "failed"]
FilingStatus = Literal[
    "collecting_materials", "needs_verification", "calculation_blocked",
    "draft_review", "ready_to_deliver", "delivered", "cancelled",
]
ReviewStatus = Literal["proposed", "accepted", "rejected", "superseded"]
RuleStatus = Literal["candidate", "under_review", "approved", "rejected", "retired"]
CalculationStatus = Literal["blocked", "completed", "stale"]
DraftStatus = Literal["blocked", "draft", "in_review", "approved", "stale"]
PackageStatus = Literal["prepared", "approved", "published", "superseded"]
RecordKind = Literal["sale", "refund", "platform_fee", "subsidy", "adjustment", "settlement", "other"]
EvidenceKind = Literal[
    "filing_file", "mvp_file", "platform_record", "settlement_batch", "bank_transaction",
    "invoice_record", "accounting_entry", "policy_source", "policy_rule", "tax_calculation",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def utc_timestamps(self):
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    raise ValueError(f"{field_name} requires UTC offset")
                setattr(self, field_name, value.astimezone(UTC))
        return self


class ReadModel(StrictModel):
    id: Id
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_created(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("UTC offset required")
        return value.astimezone(UTC)


class EvidenceRef(StrictModel):
    kind: EvidenceKind
    id: Id
    locator: str | None = None  # e.g. row 4 or page 2; never a storage path
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class Blocker(StrictModel):
    code: str
    message: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ErrorDetail(StrictModel):
    code: str
    message: str
    blockers: list[Blocker] = Field(default_factory=list)


class ErrorResponse(StrictModel):
    error: ErrorDetail


class Page(StrictModel):
    items: list[Any]
    next_cursor: str | None = None


class MerchantTaxProfileCreate(StrictModel):
    studio_id: Id
    registered_name: str = Field(min_length=1, max_length=200)
    region_code: str = Field(min_length=1, max_length=32)
    entity_type: str = Field(min_length=1, max_length=64)
    taxpayer_identity: str | None = Field(default=None, max_length=64)
    tax_identifier: str | None = Field(default=None, max_length=64)
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def valid_range(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        return self


class MerchantTaxProfileUpdate(StrictModel):
    registered_name: str | None = Field(default=None, min_length=1, max_length=200)
    region_code: str | None = Field(default=None, min_length=1, max_length=32)
    entity_type: str | None = Field(default=None, min_length=1, max_length=64)
    taxpayer_identity: str | None = Field(default=None, max_length=64)
    tax_identifier: str | None = Field(default=None, max_length=64)
    effective_to: date | None = None

    @model_validator(mode="after")
    def nonempty_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class MerchantTaxProfileRead(ReadModel, MerchantTaxProfileCreate):
    profile_version: Version
    updated_at: datetime


class FilingPeriodCreate(StrictModel):
    period_start: date
    period_end: date
    period_label: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def valid_range(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end precedes period_start")
        return self


class FilingPeriodRead(ReadModel, FilingPeriodCreate):
    pass


class RequiredMaterialRead(ReadModel):
    scope_id: Id
    material_code: str
    display_name: str
    required: bool
    accepted_types: list[str]
    rule_version: str | None = None


class SupportedScopeRead(ReadModel):
    region_code: str
    entity_type: str
    taxpayer_identity: str | None
    filing_kind: str
    platform_code: str
    platform_format_version: str
    status: ScopeStatus
    scope_version: Version
    form_version: str | None
    verified_at: datetime | None
    unsupported_reason: str | None
    required_materials: list[RequiredMaterialRead]


class ScopeCheckRequest(StrictModel):
    profile_id: Id
    filing_kind: str
    platform_code: str
    platform_format_version: str
    period_start: date
    period_end: date


class ScopeCheckResponse(StrictModel):
    supported: bool
    scope: SupportedScopeRead | None
    blockers: list[Blocker]


class FilingTaskCreate(StrictModel):
    profile_id: Id
    scope_id: Id
    period: FilingPeriodCreate
    source_order_id: Id | None = None


class FilingTaskRead(ReadModel):
    profile_id: Id
    scope_id: Id
    filing_period: FilingPeriodRead
    source_order_id: Id | None
    status: FilingStatus
    data_version: Version
    scope_version: Version
    blockers: list[Blocker]
    updated_at: datetime


class FilingFileRead(ReadModel):
    filing_task_id: Id
    original_filename: str
    mime_type: str
    file_size: StrictInt
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_status: Literal["valid", "invalid", "unsupported"]


class PlatformImportCreate(StrictModel):
    filing_task_id: Id
    filing_file_id: Id
    platform_code: str
    format_version: str
    column_map: dict[str, str] = Field(default_factory=dict)


class PlatformImportRead(ReadModel):
    filing_task_id: Id
    filing_file_id: Id
    platform_code: str
    format_version: str
    status: ImportStatus
    total_rows: StrictInt
    accepted_rows: StrictInt
    duplicate_rows: StrictInt
    rejected_rows: StrictInt
    data_version: Version
    errors: list[Blocker]


class PlatformRecordRead(ReadModel):
    filing_task_id: Id
    import_id: Id
    row_number: StrictInt
    external_id: str | None
    record_kind: RecordKind
    occurred_on: date
    settlement_external_id: str | None
    amount_cents: Money
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_version: Version
    evidence: list[EvidenceRef]


class SettlementAllocationRead(StrictModel):
    platform_record_id: Id
    amount_cents: Money


class SettlementBatchRead(ReadModel):
    filing_task_id: Id
    platform_code: str
    external_batch_id: str
    settlement_date: date | None
    expected_cents: Money | None
    received_cents: Money | None
    difference_cents: Money | None
    status: Literal["unmatched", "partial", "matched", "needs_review"]
    data_version: Version
    allocations: list[SettlementAllocationRead]
    bank_transaction_evidence: list[EvidenceRef]


class AccountingSuggestionSubmit(StrictModel):
    filing_task_id: Id
    platform_record_id: Id
    proposed_category: str
    proposed_account_code: str | None = None
    rationale: str
    confidence: Rate
    evidence: list[EvidenceRef] = Field(min_length=1)
    data_version: Version
    source_task_id: Id | None = None

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, value: str) -> str:
        if Decimal(value) > 1:
            raise ValueError("confidence must not exceed 1")
        return value


class AccountingSuggestionRead(ReadModel, AccountingSuggestionSubmit):
    status: ReviewStatus
    suggestion_version: Version


class AccountingDecision(StrictModel):
    decision: Literal["accept", "reject", "correct"]
    category: str | None = None
    account_code: str | None = None
    reason: str
    expected_data_version: Version

    @model_validator(mode="after")
    def valid_correction(self):
        if self.decision == "correct" and not self.category:
            raise ValueError("category required for correction")
        return self


class AccountingEntryRead(ReadModel):
    filing_task_id: Id
    platform_record_id: Id | None
    suggestion_id: Id | None
    category: str
    account_code: str | None
    amount_cents: Money
    evidence: list[EvidenceRef]
    confirmed_by: str
    entry_version: Version
    data_version: Version


class AccountingDecisionResult(StrictModel):
    suggestion: AccountingSuggestionRead
    entry: AccountingEntryRead | None
    data_version: Version


class PolicySourceSubmit(StrictModel):
    title: str
    issuing_authority: str
    official_url: str
    published_on: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    region_code: str
    snapshot_file_id: Id | None = None
    fetched_at: datetime
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def valid_range(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        return self


class PolicySourceRead(ReadModel, PolicySourceSubmit):
    source_version: Version
    status: Literal["candidate", "verified", "unavailable", "retired"]


class PolicyRuleSubmit(StrictModel):
    source_ids: list[Id] = Field(min_length=1)
    rule_key: str
    region_code: str
    entity_type: str
    taxpayer_identity: str | None = None
    filing_kind: str
    period_start: date
    period_end: date | None = None
    form_version: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    explanation: str
    evidence: list[EvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_range(self):
        if self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end precedes period_start")
        return self


class PolicyRuleRead(ReadModel, PolicyRuleSubmit):
    rule_version: str
    status: RuleStatus
    approved_by: str | None
    approved_at: datetime | None


class PolicyRuleDecision(StrictModel):
    decision: Literal["approve", "reject", "retire"]
    reason: str
    expected_rule_version: str


class TaxCalculationRun(StrictModel):
    expected_data_version: Version
    rule_versions: list[str]
    form_version: str


class TaxReturnDraftCreate(StrictModel):
    calculation_id: Id
    expected_data_version: Version
    form_version: str


class CalculationLine(StrictModel):
    key: str
    amount_cents: Money | None = None
    ratio: Rate | None = None
    formula: str | None = None
    evidence: list[EvidenceRef]


class TaxCalculationRead(ReadModel):
    filing_task_id: Id
    status: CalculationStatus
    data_version: Version
    rule_versions: list[str]
    form_version: str
    calculation_version: Version
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    lines: list[CalculationLine]
    blockers: list[Blocker]


class TaxFieldValue(StrictModel):
    field_key: str
    value: str | None
    evidence: list[EvidenceRef]
    calculation_line_key: str | None = None


class TaxReturnDraftRead(ReadModel):
    filing_task_id: Id
    calculation_id: Id
    form_version: str
    draft_version: Version
    data_version: Version
    rule_versions: list[str]
    status: DraftStatus
    fields: list[TaxFieldValue]
    missing_material_codes: list[str]
    blockers: list[Blocker]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str | None
    approved_at: datetime | None


class DraftReviewRequest(StrictModel):
    action: Literal["submit", "approve", "reject"]
    expected_draft_version: Version
    expected_data_version: Version
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str | None = None

    @model_validator(mode="after")
    def reject_with_reason(self):
        if self.action == "reject" and not self.reason:
            raise ValueError("reason required for rejection")
        return self


class FilingPackagePrepare(StrictModel):
    draft_id: Id
    expected_draft_version: Version
    expected_data_version: Version


class FilingPackageRead(ReadModel):
    filing_task_id: Id
    draft_id: Id
    draft_version: Version
    data_version: Version
    rule_versions: list[str]
    form_version: str
    package_version: Version
    status: PackageStatus
    manifest: list[str]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str | None
    approved_at: datetime | None
    published_at: datetime | None


class PackageAction(StrictModel):
    action: Literal["approve", "publish"]
    expected_package_version: Version
    expected_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class AgentSuggestionEnvelope(StrictModel):
    schema_version: Literal["2.0"]
    filing_task_id: Id
    source_task_id: Id
    data_version: Version
    suggestions: list[AccountingSuggestionSubmit]


class AgentPolicySourceEnvelope(StrictModel):
    schema_version: Literal["2.0"]
    filing_task_id: Id
    source_task_id: Id
    data_version: Version
    sources: list[PolicySourceSubmit]


class AgentPolicyRuleEnvelope(StrictModel):
    schema_version: Literal["2.0"]
    filing_task_id: Id
    source_task_id: Id
    data_version: Version
    rules: list[PolicyRuleSubmit]
