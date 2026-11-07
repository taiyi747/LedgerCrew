from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class ExceptionSupplementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exception_id: str
    order_id: str
    actor_id: str
    explanation: str | None
    file_id: str | None
    created_at: datetime


class ExceptionDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["resolve", "request_supplement", "reanalyze", "correct_classification", "accept_unresolved"]
    reason: str = Field(min_length=1, max_length=5000)
    target_version: StrictInt = Field(ge=1)
    expected_revision: StrictInt | None = Field(default=None, ge=1)
    classification_after: str | None = Field(default=None, max_length=100)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def check_classification(self) -> "ExceptionDecisionCreate":
        if self.decision == "correct_classification" and not (self.classification_after or "").strip():
            raise ValueError("classification_after is required for correction")
        if self.decision != "correct_classification" and self.classification_after is not None:
            raise ValueError("classification_after is only valid for correction")
        return self


class ExceptionDecisionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exception_id: str
    decision: Literal["resolve", "request_supplement", "reanalyze", "correct_classification", "accept_unresolved"]
    reason: str = Field(min_length=1, max_length=5000)
    classification_after: str | None = Field(default=None, max_length=100)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def check_classification(self) -> "ExceptionDecisionItem":
        if self.decision == "correct_classification" and not (self.classification_after or "").strip():
            raise ValueError("classification_after is required for correction")
        if self.decision != "correct_classification" and self.classification_after is not None:
            raise ValueError("classification_after is only valid for correction")
        return self


class ExceptionDecisionBatchCreate(BaseModel):
    """一批异常处置决定：绑定同一材料版本与目标报告版本，成功后只推进一次输入版本。"""

    model_config = ConfigDict(extra="forbid")

    expected_revision: StrictInt | None = Field(default=None, ge=1)
    target_version: StrictInt = Field(ge=1)
    decisions: list[ExceptionDecisionItem] = Field(min_length=1, max_length=200)


class ExceptionDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    exception_id: str
    order_id: str
    decision: str
    actor_id: str
    reason: str
    target_version: int
    classification_before: str | None
    classification_after: str | None
    created_at: datetime


class ReportVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    version: int
    status: str
    reconciliation_batch_id: str
    source_revision: int | None
    report_content: str
    financial_summary: dict[str, int]
    reconciliation_summary: dict[str, Any]
    exception_snapshot: list[dict[str, Any]]
    evidence_references: list[str]
    unresolved_items: list[str]
    content_hash: str
    created_at: datetime
    approved_at: datetime | None
    approved_by: str | None
    published_at: datetime | None


class ReportReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=5000)
