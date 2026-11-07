"""Versioned human review of persisted Agent outputs.

Revision ID: 0012_agent_result_review
Revises: 0011_feedback
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_agent_result_review"
down_revision = "0011_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_result_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("agent_tasks.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("original_output", sa.JSON(), nullable=False),
        sa.Column("revised_output", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.String(100), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("task_id", "version", name="uq_agent_result_review_version"),
        sa.CheckConstraint("decision IN ('confirmed','corrected','rejected')", name="ck_agent_review_decision"),
    )
    op.create_index("ix_agent_result_reviews_task", "agent_result_reviews", ["task_id", "version"])


def downgrade() -> None:
    op.drop_index("ix_agent_result_reviews_task", table_name="agent_result_reviews")
    op.drop_table("agent_result_reviews")
