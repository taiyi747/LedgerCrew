from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime, utc_now
from app.models.records import new_id


class StatementImport(Base):
    __tablename__ = "statement_imports"
    __table_args__ = (
        UniqueConstraint("uploaded_file_id", name="uq_statement_imports_file"),
        Index("ix_statement_imports_order_created", "order_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    uploaded_file_id: Mapped[str] = mapped_column(ForeignKey("uploaded_files.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    success_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    column_map_json: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint("statement_import_id", "row_number", name="uq_bank_transactions_import_row"),
        UniqueConstraint("statement_import_id", "external_id", name="uq_bank_transactions_import_external"),
        CheckConstraint("direction IN ('IN','OUT')", name="ck_bank_transactions_direction"),
        CheckConstraint("amount_cents > 0", name="ck_bank_transactions_amount"),
        Index("ix_bank_transactions_order_date", "order_id", "transaction_date"),
        Index("ix_bank_transactions_order_counterparty", "order_id", "normalized_counterparty"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False)
    statement_import_id: Mapped[str] = mapped_column(ForeignKey("statement_imports.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    transaction_date: Mapped[date] = mapped_column(nullable=False)
    counterparty: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_counterparty: Mapped[str] = mapped_column(String(300), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_row_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)


class StatementImportError(Base):
    __tablename__ = "statement_import_errors"
    __table_args__ = (UniqueConstraint("statement_import_id", "row_number", name="uq_statement_import_errors_import_row"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    statement_import_id: Mapped[str] = mapped_column(ForeignKey("statement_imports.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_row_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
