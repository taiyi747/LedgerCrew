"""Persist Agent idempotency, contract version, correlation, and checkpoints.

Revision ID: 0006_agent_integration
Revises: 0005_reconciliation
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_agent_integration"
down_revision = "0005_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("input_schema_version", sa.String(20), nullable=True))
    op.add_column("agent_runs", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.add_column("agent_runs", sa.Column("correlation_id", sa.String(100), nullable=True))
    op.add_column("agent_runs", sa.Column("checkpoint_data", sa.JSON(), nullable=True))
    op.add_column("agent_tasks", sa.Column("idempotency_key", sa.String(100), nullable=True))
    op.add_column("agent_tasks", sa.Column("correlation_id", sa.String(100), nullable=True))
    op.add_column("agent_tasks", sa.Column("input_schema_version", sa.String(20), nullable=True))
    op.add_column("agent_tasks", sa.Column("provider_metadata", sa.JSON(), nullable=True))
    op.add_column("agent_tasks", sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False))
    op.create_index("ix_agent_tasks_order_idempotency", "agent_tasks", ["order_id", "idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_agent_tasks_order_idempotency", table_name="agent_tasks")
    with op.batch_alter_table("agent_tasks") as batch_op:
        batch_op.drop_column("attempt_count")
        batch_op.drop_column("provider_metadata")
        batch_op.drop_column("input_schema_version")
        batch_op.drop_column("correlation_id")
        batch_op.drop_column("idempotency_key")
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("checkpoint_data")
        batch_op.drop_column("correlation_id")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("input_schema_version")
