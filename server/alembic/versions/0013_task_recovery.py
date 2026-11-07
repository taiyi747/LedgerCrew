"""Finite task retry, cancellation and timeout history.

Revision ID: 0013_task_recovery
Revises: 0012_agent_result_review
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_task_recovery"
down_revision = "0012_agent_result_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, constraint in (("agent_runs", "ck_agent_runs_status"),
                              ("agent_tasks", "ck_agent_tasks_status")):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(constraint, type_="check")
            batch.create_check_constraint(constraint,
                "status IN ('queued','running','paused','succeeded','failed','cancelled','retrying','timeout')")
    op.create_table(
        "agent_task_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_task_history_task_created", "agent_task_history", ["task_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_task_history_task_created", table_name="agent_task_history")
    op.drop_table("agent_task_history")
    for table, constraint in (("agent_runs", "ck_agent_runs_status"),
                              ("agent_tasks", "ck_agent_tasks_status")):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(constraint, type_="check")
            batch.create_check_constraint(constraint,
                "status IN ('queued','running','paused','succeeded','failed')")
