"""Persist backend Agent model request budgets and metadata.

Revision ID: 0014_agent_model_artifacts
Revises: 0013_task_recovery
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_agent_model_artifacts"
down_revision = "0013_task_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_model_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("task_id", "idempotency_key", name="uq_agent_model_artifacts_idempotency"),
    )
    op.create_index("ix_agent_model_artifacts_task_kind", "agent_model_artifacts", ["task_id", "kind", "id"])


def downgrade() -> None:
    op.drop_index("ix_agent_model_artifacts_task_kind", table_name="agent_model_artifacts")
    op.drop_table("agent_model_artifacts")
