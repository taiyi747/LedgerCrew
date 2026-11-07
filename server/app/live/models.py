from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now


def new_id():
    return str(uuid4())


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("order_id", "idempotency_key", name="uq_workflow_request"),
        Index("ix_workflow_queue", "status", "kind", "created_at"),
        Index(
            "uq_workflow_active_order",
            "order_id",
            unique=True,
            sqlite_where=text("kind = 'processing' AND status IN ('queued','running','paused')"),
        ),
        CheckConstraint("requests_used >= 0 AND request_limit > 0", name="ck_workflow_budget"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="processing", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    stage: Mapped[str] = mapped_column(String(100), default="supervisor", nullable=False)
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    requests_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    request_limit: Mapped[int] = mapped_column(Integer, default=64, nullable=False)
    wait_reason: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    checkpoint_id: Mapped[str | None] = mapped_column(String(100))
    pending_request_id: Mapped[str | None] = mapped_column(String(100))
    source_message_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )


class Delegation(Base):
    __tablename__ = "workflow_delegations"
    __table_args__ = (UniqueConstraint("workflow_run_id", "operation_key", name="uq_delegation_operation"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(50), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    input_refs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    receipts: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    todos: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )


class WorkflowArtifact(Base):
    __tablename__ = "workflow_artifacts"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "operation_key", name="uq_workflow_artifact_operation"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(100), nullable=False)
    input_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class OrderMessage(Base):
    __tablename__ = "order_messages"
    __table_args__ = (UniqueConstraint("order_id", "client_message_id", name="uq_order_message_client"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    workflow_run_id: Mapped[str | None] = mapped_column(ForeignKey("workflow_runs.id"))
    client_message_id: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    file_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    input_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
