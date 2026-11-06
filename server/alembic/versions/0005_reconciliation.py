"""Deterministic invoice reconciliation records.

Revision ID: 0005_reconciliation
Revises: 0004_statement_imports
"""

from alembic import op
import sqlalchemy as sa

from app.db.types import UTCDateTime
from app.models.reconciliation import EXCEPTION_TYPES

revision = "0005_reconciliation"
down_revision = "0004_statement_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("source_file_id", sa.String(36), sa.ForeignKey("uploaded_files.id"), nullable=False),
        sa.Column("invoice_number", sa.String(100), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("seller", sa.String(300), nullable=True),
        sa.Column("buyer", sa.String(300), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("tax_cents", sa.Integer(), nullable=True),
        sa.Column("total_amount_cents", sa.Integer(), nullable=True),
        sa.Column("extraction_status", sa.String(20), nullable=False),
        sa.Column("confidence_data", sa.JSON(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("amount_cents IS NULL OR amount_cents >= 0", name="ck_invoice_amount"),
        sa.CheckConstraint("tax_cents IS NULL OR tax_cents >= 0", name="ck_invoice_tax"),
        sa.CheckConstraint("total_amount_cents IS NULL OR total_amount_cents > 0", name="ck_invoice_total"),
        sa.CheckConstraint("extraction_status IN ('ready','needs_review','invalid')", name="ck_invoice_extraction_status"),
    )
    op.create_index("ix_invoice_records_order_date", "invoice_records", ["order_id", "issue_date"])
    op.create_index("ix_invoice_records_order_number", "invoice_records", ["order_id", "invoice_number"])
    op.create_table(
        "reconciliation_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("batch_number", sa.Integer(), nullable=False),
        sa.Column("income_total_cents", sa.Integer(), nullable=False),
        sa.Column("expense_total_cents", sa.Integer(), nullable=False),
        sa.Column("net_cash_change_cents", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("unmatched_count", sa.Integer(), nullable=False),
        sa.Column("exception_count", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("order_id", "batch_number", name="uq_reconciliation_batch_number"),
        sa.CheckConstraint("batch_number > 0", name="ck_reconciliation_batch_number"),
    )
    op.create_index("ix_reconciliation_batches_order_created", "reconciliation_batches", ["order_id", "created_at"])
    op.create_table(
        "reconciliation_matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("reconciliation_batches.id"), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoice_records.id"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("bank_transactions.id"), nullable=False),
        sa.Column("match_status", sa.String(16), nullable=False),
        sa.Column("difference_cents", sa.Integer(), nullable=False),
        sa.Column("match_rule", sa.String(100), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("batch_id", "invoice_id", name="uq_reconciliation_match_invoice"),
        sa.UniqueConstraint("batch_id", "transaction_id", name="uq_reconciliation_match_transaction"),
        sa.CheckConstraint("match_status = 'matched'", name="ck_reconciliation_match_status"),
        sa.CheckConstraint("difference_cents = 0", name="ck_reconciliation_match_difference"),
    )
    op.create_index("ix_reconciliation_matches_order_batch", "reconciliation_matches", ["order_id", "batch_id"])
    op.create_table(
        "exception_tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("exception_no", sa.String(50), nullable=False),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("reconciliation_batches.id"), nullable=False),
        sa.Column("exception_type", sa.String(40), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoice_records.id"), nullable=True),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("bank_transactions.id"), nullable=True),
        sa.Column("related_amount_cents", sa.Integer(), nullable=True),
        sa.Column("difference_cents", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("exception_no", name="uq_exception_ticket_no"),
        sa.CheckConstraint("exception_type IN (" + ",".join(f"'{value}'" for value in EXCEPTION_TYPES) + ")", name="ck_exception_ticket_type"),
        sa.CheckConstraint("status IN ('open','waiting_customer','waiting_owner','resolved','accepted_unresolved')", name="ck_exception_ticket_status"),
    )
    op.create_index("ix_exception_tickets_order_status", "exception_tickets", ["order_id", "status"])
    op.create_index("ix_exception_tickets_batch", "exception_tickets", ["batch_id"])


def downgrade() -> None:
    op.drop_table("exception_tickets")
    op.drop_table("reconciliation_matches")
    op.drop_table("reconciliation_batches")
    op.drop_table("invoice_records")
