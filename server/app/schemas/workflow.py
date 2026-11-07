from pydantic import BaseModel, Field

from app.agents.contracts import ReviewAction


class WorkflowReplyCreate(BaseModel):
    action: ReviewAction
    comment: str = Field(default="", max_length=4000)
    report_version: int | None = Field(default=None, ge=1)
