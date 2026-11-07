from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.records import new_id


EXCEPTION_TYPES = (
    "AMOUNT_MISMATCH", "MISSING_INVOICE", "MISSING_TRANSACTION", "DUPLICATE_INVOICE",
    "DUPLICATE_TRANSACTION", "MULTIPLE_CANDIDATES", "INVOICE_FIELD_MISSING",
    "COUNTERPARTY_OR_DATE_CONFLICT",
)


class InvoiceRecord(Base):
    __tablename__ = "invoice_records"
    __table_args__ = (
        CheckConstraint("amount_cents IS NULL OR amount_cents >= 0", name="ck_invoice_amount"),
        CheckConstraint("tax_cents IS NULL OR tax_cents >= 0", name="ck_invoice_tax"),
        CheckConstraint("total_amount_cents IS NULL OR total_amount_cents > 0", name="ck_invoice_total"),
        CheckConstraint("extraction_status IN ('ready','needs_review','invalid')", name="ck_invoice_extraction_status"),
        Index("ix_invoice_records_order_date", "order_id", "issue_date"),
        Index("ix_invoice_records_order_number", "order_id", "invoice_number"),
        Index("ix_invoice_records_source_task", "source_task_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("uploaded_files.id"), nullable=False)
    source_task_id: Mapped[str | None] = mapped_column(ForeignKey("agent_tasks.id"), nullable=True)
    material_review_task_id: Mapped[str | None] = mapped_column(ForeignKey("agent_tasks.id"), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(nullable=True)
    seller: Mapped[str | None] = mapped_column(String(300), nullable=True)
    buyer: Mapped[str | None] = mapped_column(String(300), nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ReconciliationBatch(Base):
    __tablename__ = "reconciliation_batches"
    __table_args__ = (
        UniqueConstraint("order_id", "batch_number", name="uq_reconciliation_batch_number"),
        CheckConstraint("batch_number > 0", name="ck_reconciliation_batch_number"),
        Index("ix_reconciliation_batches_order_created", "order_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False)
    income_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    expense_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    net_cash_change_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unmatched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    exception_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ReconciliationMatch(Base):
    __tablename__ = "reconciliation_matches"
    __table_args__ = (
        UniqueConstraint("batch_id", "invoice_id", name="uq_reconciliation_match_invoice"),
        UniqueConstraint("batch_id", "transaction_id", name="uq_reconciliation_match_transaction"),
        CheckConstraint("match_status = 'matched'", name="ck_reconciliation_match_status"),
        CheckConstraint("difference_cents = 0", name="ck_reconciliation_match_difference"),
        Index("ix_reconciliation_matches_order_batch", "order_id", "batch_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    batch_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_batches.id"), nullable=False)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoice_records.id"), nullable=False)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("bank_transactions.id"), nullable=False)
    match_status: Mapped[str] = mapped_column(String(16), default="matched", nullable=False)
    difference_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    match_rule: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class ExceptionTicket(Base):
    __tablename__ = "exception_tickets"
    __table_args__ = (
        UniqueConstraint("exception_no", name="uq_exception_ticket_no"),
        CheckConstraint("exception_type IN (" + ",".join(f"'{value}'" for value in EXCEPTION_TYPES) + ")", name="ck_exception_ticket_type"),
        CheckConstraint("status IN ('open','waiting_customer','waiting_owner','resolved','accepted_unresolved')", name="ck_exception_ticket_status"),
        Index("ix_exception_tickets_order_status", "order_id", "status"),
        Index("ix_exception_tickets_batch", "batch_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    exception_no: Mapped[str] = mapped_column(String(50), nullable=False)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    batch_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_batches.id"), nullable=False)
    exception_type: Mapped[str] = mapped_column(String(40), nullable=False)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoice_records.id"), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(ForeignKey("bank_transactions.id"), nullable=True)
    related_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difference_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    business_classification: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False)
