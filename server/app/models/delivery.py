from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.records import new_id


class ExceptionSupplement(Base):
    __tablename__ = "exception_supplements"
    __table_args__ = (
        CheckConstraint("explanation IS NOT NULL OR file_id IS NOT NULL", name="ck_exception_supplement_content"),
        Index("ix_exception_supplements_exception_created", "exception_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exception_id: Mapped[str] = mapped_column(ForeignKey("exception_tickets.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("uploaded_files.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ExceptionDecision(Base):
    __tablename__ = "exception_decisions"
    __table_args__ = (
        CheckConstraint("decision IN ('resolve','request_supplement','reanalyze','correct_classification','accept_unresolved')",
                        name="ck_exception_decision_type"),
        CheckConstraint("target_version > 0", name="ck_exception_decision_target_version"),
        Index("ix_exception_decisions_exception_created", "exception_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exception_id: Mapped[str] = mapped_column(ForeignKey("exception_tickets.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    target_version: Mapped[int] = mapped_column(Integer, nullable=False)
    classification_before: Mapped[str | None] = mapped_column(String(100), nullable=True)
    classification_after: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ReportVersion(Base):
    __tablename__ = "report_versions"
    __table_args__ = (
        UniqueConstraint("order_id", "version", name="uq_report_versions_order_version"),
        UniqueConstraint("source_task_id", name="uq_report_versions_source_task"),
        CheckConstraint("version > 0", name="ck_report_version_positive"),
        CheckConstraint("status IN ('draft','in_review','approved','published','superseded')",
                        name="ck_report_version_status"),
        Index("ix_report_versions_order_status", "order_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    source_task_id: Mapped[str | None] = mapped_column(ForeignKey("agent_tasks.id"), nullable=True)
    reconciliation_batch_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_batches.id"), nullable=False)
    report_content: Mapped[str] = mapped_column(Text, nullable=False)
    financial_summary: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    reconciliation_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    exception_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence_references: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    unresolved_items: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class ReportReviewAction(Base):
    __tablename__ = "report_review_actions"
    __table_args__ = (
        CheckConstraint("action IN ('approved','rejected')", name="ck_report_review_action"),
        Index("ix_report_review_actions_report_created", "report_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(ForeignKey("report_versions.id"), nullable=False)
    report_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
