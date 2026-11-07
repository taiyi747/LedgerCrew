from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.records import new_id


class AgentResultReview(Base):
    __tablename__ = "agent_result_reviews"
    __table_args__ = (
        UniqueConstraint("task_id", "version", name="uq_agent_result_review_version"),
        CheckConstraint("decision IN ('confirmed','corrected','rejected')", name="ck_agent_review_decision"),
        Index("ix_agent_result_reviews_task", "task_id", "version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_tasks.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    original_output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    revised_output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
