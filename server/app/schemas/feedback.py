from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["bug", "question", "request", "other"]
    message: str = Field(min_length=1, max_length=5000)
    order_id: str | None = None
    run_id: str | None = None


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    studio_id: str
    order_id: str | None
    run_id: str | None
    category: str
    status: str
    message: str
    submitted_by: str
    handled_by: str | None
    handled_at: datetime | None
    created_at: datetime


class FeedbackActionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["in_progress", "resolved", "rejected"]
    note: str = Field(min_length=1, max_length=5000)


class FeedbackActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    feedback_id: str
    actor_id: str
    action: str
    note: str
    created_at: datetime
