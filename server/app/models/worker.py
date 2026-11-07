"""Persistent identity and liveness for task executors."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now


class WorkerInstance(Base):
    __tablename__ = "worker_instances"
    __table_args__ = (
        CheckConstraint("status IN ('running','stopped','lost')", name="ck_worker_instances_status"),
        Index("ix_worker_instances_status_heartbeat", "status", "last_heartbeat_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    current_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
