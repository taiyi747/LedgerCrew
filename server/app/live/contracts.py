import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


Role = Literal["invoice_processing", "data_reconciliation", "customer_reception", "risk_delivery"]


class Assignment(Contract):
    agent_role: Role
    task_type: Literal[
        "invoice_batch",
        "reconcile_order",
        "intake",
        "questions",
        "risk_summary",
        "report_draft",
        "answer_question",
    ]
    goal: str = Field(min_length=1, max_length=1000)
    input_refs: list[str] = Field(default_factory=list)


class SupervisorDecision(Contract):
    action: Literal["delegated", "waiting_owner", "waiting_customer", "completed"]
    summary: str


class RoleResult(Contract):
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)


class ChatReply(Contract):
    answer: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("answer")
    @classmethod
    def qualitative_answer(cls, value):
        if re.search(r"[0-9]", value):
            raise ValueError("金额和数量请引用后端明细，答复使用定性文字。")
        return value


class RunCreate(Contract):
    idempotency_key: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)


class MessageCreate(Contract):
    client_message_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=3000)
    intent: Literal["question", "materials"] = "question"
    file_ids: list[str] = Field(default_factory=list)


class WorkflowWait(Contract):
    run_id: str


class WorkflowWake(Contract):
    run_id: str


ROLES = {
    "supervisor": {"name": "财税运营总管", "workspace": "supervisor", "model": "Pro"},
    "customer_reception": {"name": "客户服务 Agent", "workspace": "reception", "model": "Flash"},
    "invoice_processing": {"name": "票据处理 Agent", "workspace": "ticketing", "model": "Flash"},
    "data_reconciliation": {"name": "数据核对 Agent", "workspace": "reconcile", "model": "Pro"},
    "risk_delivery": {"name": "风险与交付 Agent", "workspace": "delivery", "model": "Pro"},
}
RUNNER_ROLES = {
    "supervisor": "supervisor",
    "invoice_processing": "invoice",
    "data_reconciliation": "reconciliation",
    "customer_reception": "customer_service",
    "risk_delivery": "delivery",
}
TASK_ROLE = {
    "invoice_batch": "invoice_processing",
    "reconcile_order": "data_reconciliation",
    "intake": "customer_reception",
    "questions": "customer_reception",
    "risk_summary": "risk_delivery",
    "report_draft": "risk_delivery",
    "answer_question": "customer_reception",
}
