"""Statement imports and normalized bank transactions.

Revision ID: 0004_statement_imports
Revises: 0003_required_order_fields
"""

from alembic import op
import sqlalchemy as sa

from app.db.types import UTCDateTime

revision = "0004_statement_imports"
down_revision = "0003_required_order_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "statement_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("uploaded_file_id", sa.String(36), sa.ForeignKey("uploaded_files.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("success_rows", sa.Integer(), nullable=False),
        sa.Column("failed_rows", sa.Integer(), nullable=False),
        sa.Column("column_map_json", sa.JSON(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("uploaded_file_id", name="uq_statement_imports_file"),
    )
    op.create_index("ix_statement_imports_order_created", "statement_imports", ["order_id", "created_at"])
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("statement_import_id", sa.String(36), sa.ForeignKey("statement_imports.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("counterparty", sa.String(300), nullable=False),
        sa.Column("normalized_counterparty", sa.String(300), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("raw_row_json", sa.JSON(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("statement_import_id", "row_number", name="uq_bank_transactions_import_row"),
        sa.UniqueConstraint("statement_import_id", "external_id", name="uq_bank_transactions_import_external"),
        sa.CheckConstraint("direction IN ('IN','OUT')", name="ck_bank_transactions_direction"),
        sa.CheckConstraint("amount_cents > 0", name="ck_bank_transactions_amount"),
    )
    op.create_index("ix_bank_transactions_order_date", "bank_transactions", ["order_id", "transaction_date"])
    op.create_index("ix_bank_transactions_order_counterparty", "bank_transactions", ["order_id", "normalized_counterparty"])
    op.create_table(
        "statement_import_errors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("statement_import_id", sa.String(36), sa.ForeignKey("statement_imports.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("raw_row_json", sa.JSON(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("statement_import_id", "row_number", name="uq_statement_import_errors_import_row"),
    )


def downgrade() -> None:
    op.drop_table("statement_import_errors")
    op.drop_table("bank_transactions")
    op.drop_table("statement_imports")
