from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now


def new_id():
    return str(uuid4())


class IntakeSession(Base):
    __tablename__ = "intake_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="collecting", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    studio_id: Mapped[str | None] = mapped_column(ForeignKey("studios.id"))
    studio_name: Mapped[str | None] = mapped_column(String(200))
    period_start: Mapped[date | None] = mapped_column()
    period_end: Mapped[date | None] = mapped_column()
    profile_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    service_code: Mapped[str] = mapped_column(String(60), default="monthly_records", nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    confirmation_key: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )


class IntakeFile(Base):
    __tablename__ = "intake_files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    intake_id: Mapped[str] = mapped_column(ForeignKey("intake_sessions.id"), index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_classified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archive_file_id: Mapped[str | None] = mapped_column(ForeignKey("intake_files.id"))
    archive_entry_path: Mapped[str | None] = mapped_column(String(500))
    replaced_by_file_id: Mapped[str | None] = mapped_column(String(36))
    order_file_id: Mapped[str | None] = mapped_column(String(36))
    derived_from_file_id: Mapped[str | None] = mapped_column(ForeignKey("intake_files.id"))
    derivation_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class IntakeMessage(Base):
    __tablename__ = "intake_messages"
    __table_args__ = (UniqueConstraint("intake_id", "client_message_id", name="uq_intake_message_client"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    intake_id: Mapped[str] = mapped_column(ForeignKey("intake_sessions.id"), nullable=False)
    client_message_id: Mapped[str | None] = mapped_column(String(100))
    job_id: Mapped[str | None] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    file_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class IntakeJob(Base):
    __tablename__ = "intake_jobs"
    __table_args__ = (
        UniqueConstraint("intake_id", "operation_key", name="uq_intake_job_operation"),
        Index("ix_intake_job_queue", "kind", "status", "created_at"),
        Index(
            "uq_intake_active_precheck",
            "intake_id",
            unique=True,
            sqlite_where=text("kind='precheck' AND status IN ('queued','running')"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    intake_id: Mapped[str] = mapped_column(ForeignKey("intake_sessions.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(100), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    requests_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(36))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    artifacts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )


class IntakeEvent(Base):
    __tablename__ = "intake_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intake_id: Mapped[str] = mapped_column(ForeignKey("intake_sessions.id"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
