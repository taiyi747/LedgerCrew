from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class AgentReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["confirmed", "corrected", "rejected"]
    note: str = Field(min_length=1, max_length=5000)
    revised_output: dict[str, JsonValue] | None = None


class AgentReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    version: int
    decision: str
    original_output: dict[str, Any]
    revised_output: dict[str, Any] | None
    note: str
    reviewer_id: str
    reviewed_at: datetime


class AgentReviewStats(BaseModel):
    confirmed: int
    corrected: int
    rejected: int
    reviewed_tasks: int
