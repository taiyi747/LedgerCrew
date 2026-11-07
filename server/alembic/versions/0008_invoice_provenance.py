"""Link extracted invoices to accepted review and extraction tasks.

Revision ID: 0008_invoice_provenance
Revises: 0007_delivery
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_invoice_provenance"
down_revision = "0007_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invoice_records") as batch_op:
        batch_op.add_column(sa.Column("source_task_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("material_review_task_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key("fk_invoice_records_source_task", "agent_tasks", ["source_task_id"], ["id"])
        batch_op.create_foreign_key("fk_invoice_records_review_task", "agent_tasks", ["material_review_task_id"], ["id"])
    op.create_index("ix_invoice_records_source_task", "invoice_records", ["source_task_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_invoice_records_source_task", table_name="invoice_records")
    with op.batch_alter_table("invoice_records") as batch_op:
        batch_op.drop_constraint("fk_invoice_records_review_task", type_="foreignkey")
        batch_op.drop_constraint("fk_invoice_records_source_task", type_="foreignkey")
        batch_op.drop_column("material_review_task_id")
        batch_op.drop_column("source_task_id")
