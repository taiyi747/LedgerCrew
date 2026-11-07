from datetime import date
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntakeCreate(Contract):
    service_code: Literal["monthly_records"] = "monthly_records"


class ProfileUpdate(Contract):
    expected_revision: int = Field(ge=1)
    studio_id: str | None = None
    studio_name: str = Field(min_length=1, max_length=200)
    period_start: date
    period_end: date
    profile_confirmed: bool = True

    @model_validator(mode="after")
    def period(self):
        if self.period_end < self.period_start:
            raise ValueError("账期结束日期早于开始日期")
        if not self.studio_name.strip():
            raise ValueError("请输入工作室名称")
        return self


class FileUpdate(Contract):
    expected_revision: int = Field(ge=1)
    category: Literal["invoice_image", "supporting_material", "unclassified"] | None = None
    included: bool | None = None
    replaces_file_id: str | None = None


class PrecheckCreate(Contract):
    expected_revision: int = Field(ge=1)


class ConfirmCreate(PrecheckCreate):
    precheck_id: str
    service_version: int
    idempotency_key: str = Field(min_length=1, max_length=100)
    acknowledged_warning_ids: list[str] = Field(default_factory=list)


class MessageCreate(Contract):
    client_message_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=3000)
    intent: Literal["question", "materials"] = "question"
    file_ids: list[str] = Field(default_factory=list)


class ImageSample(Contract):
    file_id: str
    category: Literal["invoice_image", "supporting_material", "unclassified"]
    readable: bool
    explanation: str


class PrecheckNarrative(Contract):
    # Intermediate SDK turns may end after tool calls. The intake controller verifies
    # persisted receipts and the saved candidate before exposing any final answer.
    accepts_tool_progress: ClassVar[bool] = True
    summary: str = Field(min_length=1)
    questions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class IntakeAnswer(Contract):
    answer: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


SERVICE = {
    "code": "monthly_records",
    "version": 1,
    "name": "票据整理＋流水核对＋异常报告",
    "price_cents": 1990,
    "currency": "CNY",
    "is_simulated": True,
    "deliverables": ["票据整理结果", "流水核对明细", "异常清单与核对报告"],
    "delivery_note": "材料确认后进入处理，完成老板审核后交付",
    "requirements": {
        "invoice_limit": 20,
        "statement_count": 1,
        "csv_row_limit": 200,
        "image_bytes": 5242880,
        "csv_bytes": 2097152,
        "zip_bytes": 26214400,
    },
}


class MaterialRead(Contract):
    id: str
    original_filename: str
    category: str
    mime_type: str
    file_size: int
    sha256: str
    validation_status: str
    included: bool
    user_classified: bool
    archive_file_id: str | None
    archive_entry_path: str | None
    replaced_by_file_id: str | None
    derived_from_file_id: str | None = None


class PrecheckRead(Contract):
    id: str
    status: str
    revision: int
    requests_used: int
    request_limit: int | None
    result: dict | None
    error: str | None
    todos: list[dict] = Field(default_factory=list)


class ConfirmationCard(Contract):
    precheck_id: str
    revision: int
    service_version: int
    price_cents: int
    warnings: list[dict]
    deliverables: list[str]
    is_simulated: bool


class IntakeSnapshot(Contract):
    id: str
    status: str
    revision: int
    order_id: str | None
    studio_id: str | None
    studio_name: str | None
    period_start: date | None
    period_end: date | None
    profile_confirmed: bool
    service: dict
    files: list[MaterialRead]
    precheck: PrecheckRead | None
    confirmation: ConfirmationCard | None


class ConfirmResult(Contract):
    order_id: str
    order_no: str
    run_id: str
    price_cents: int


class JobQueued(Contract):
    id: str
    status: str
    requests_used: int
    request_limit: int | None
