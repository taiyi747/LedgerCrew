"""Link extracted invoices and deterministic batches to full workflow tasks.

Revision ID: 0016_workflow_provenance
Revises: 0015_worker_leases
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_workflow_provenance"
down_revision = "0015_worker_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invoice_records") as batch:
        batch.add_column(sa.Column("workflow_task_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_invoice_records_workflow_task", "agent_tasks", ["workflow_task_id"], ["id"])
        batch.create_unique_constraint("uq_invoice_workflow_file", ["workflow_task_id", "source_file_id"])
    with op.batch_alter_table("reconciliation_batches") as batch:
        batch.add_column(sa.Column("workflow_task_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_reconciliation_workflow_task", "agent_tasks", ["workflow_task_id"], ["id"])
        batch.create_unique_constraint("uq_reconciliation_workflow_task", ["workflow_task_id"])
    with op.batch_alter_table("report_versions") as batch:
        batch.add_column(sa.Column("workflow_task_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("workflow_report_version", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_report_versions_workflow_task", "agent_tasks", ["workflow_task_id"], ["id"])
        batch.create_unique_constraint("uq_report_workflow_version", ["workflow_task_id", "workflow_report_version"])


def downgrade() -> None:
    with op.batch_alter_table("report_versions") as batch:
        batch.drop_constraint("uq_report_workflow_version", type_="unique")
        batch.drop_constraint("fk_report_versions_workflow_task", type_="foreignkey")
        batch.drop_column("workflow_report_version")
        batch.drop_column("workflow_task_id")
    with op.batch_alter_table("reconciliation_batches") as batch:
        batch.drop_constraint("uq_reconciliation_workflow_task", type_="unique")
        batch.drop_constraint("fk_reconciliation_workflow_task", type_="foreignkey")
        batch.drop_column("workflow_task_id")
    with op.batch_alter_table("invoice_records") as batch:
        batch.drop_constraint("uq_invoice_workflow_file", type_="unique")
        batch.drop_constraint("fk_invoice_records_workflow_task", type_="foreignkey")
        batch.drop_column("workflow_task_id")
