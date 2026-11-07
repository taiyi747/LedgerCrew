from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.integrations.agents.contracts import AgentRole, AgentStatus, contract_for


class AgentTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    agent_role: AgentRole
    task_type: str
    input_schema_version: str = "1.0"
    idempotency_key: str = Field(min_length=1, max_length=100)
    correlation_id: str = Field(min_length=1, max_length=100)
    input_payload: dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_payload(self) -> "AgentTaskCreate":
        input_model, _ = contract_for(self.agent_role, self.task_type, self.input_schema_version)
        payload = input_model.model_validate(self.input_payload)
        if payload.order_id != self.order_id:
            raise ValueError("Payload order_id must match task order_id")
        return self


class AgentTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    run_id: str
    task_key: str
    idempotency_key: str | None
    correlation_id: str | None
    input_schema_version: str | None
    agent_name: str
    task_type: str
    status: AgentStatus
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    provider_metadata: dict[str, Any] | None
    attempt_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    agent_name: str
    task_type: str
    input_schema_version: str | None
    idempotency_key: str | None
    correlation_id: str | None
    status: AgentStatus
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    checkpoint_data: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class WorkflowEventRead(BaseModel):
    event_id: int
    order_id: str
    run_id: str | None
    task_id: str | None
    event_type: str
    payload: dict[str, Any] | None
    created_at: datetime


class AgentTaskHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str
    from_status: str | None
    to_status: str
    reason: str | None
    created_at: datetime
