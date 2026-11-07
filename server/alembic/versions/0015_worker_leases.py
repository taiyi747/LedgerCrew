"""Durable worker heartbeats and fenced task leases.

Revision ID: 0015_worker_leases
Revises: 0014_agent_model_artifacts
"""

import sqlalchemy as sa

from alembic import op

revision = "0015_worker_leases"
down_revision = "0014_agent_model_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_instances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=False),
        sa.Column("stopped_at", sa.DateTime(), nullable=True),
        sa.Column("current_task_id", sa.String(36), nullable=True),
        sa.CheckConstraint("status IN ('running','stopped','lost')", name="ck_worker_instances_status"),
    )
    op.create_index("ix_worker_instances_status_heartbeat", "worker_instances",
                    ["status", "last_heartbeat_at"])
    with op.batch_alter_table("agent_tasks") as batch:
        batch.add_column(sa.Column("lease_owner", sa.String(36), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key("fk_agent_tasks_lease_owner", "worker_instances", ["lease_owner"], ["id"])
    op.create_index("ix_agent_tasks_claim", "agent_tasks", ["status", "next_attempt_at", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_tasks_claim", table_name="agent_tasks")
    with op.batch_alter_table("agent_tasks") as batch:
        batch.drop_constraint("fk_agent_tasks_lease_owner", type_="foreignkey")
        batch.drop_column("next_attempt_at")
        batch.drop_column("lease_generation")
        batch.drop_column("lease_expires_at")
        batch.drop_column("lease_owner")
    op.drop_index("ix_worker_instances_status_heartbeat", table_name="worker_instances")
    op.drop_table("worker_instances")
