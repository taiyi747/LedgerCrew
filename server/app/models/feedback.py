from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.records import new_id


class CustomerFeedback(Base):
    __tablename__ = "customer_feedback"
    __table_args__ = (
        CheckConstraint("category IN ('bug','question','request','other')", name="ck_feedback_category"),
        CheckConstraint("status IN ('open','in_progress','resolved','rejected')", name="ck_feedback_status"),
        Index("ix_feedback_studio_created", "studio_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    studio_id: Mapped[str] = mapped_column(ForeignKey("studios.id"), nullable=False)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    handled_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False)


class FeedbackAction(Base):
    __tablename__ = "feedback_actions"
    __table_args__ = (Index("ix_feedback_actions_feedback_created", "feedback_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    feedback_id: Mapped[str] = mapped_column(ForeignKey("customer_feedback.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
