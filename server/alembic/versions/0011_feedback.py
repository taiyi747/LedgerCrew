"""Tenant-scoped customer feedback and handling history.

Revision ID: 0011_feedback
Revises: 0010_sandbox_payments
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_feedback"
down_revision = "0010_sandbox_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("studio_id", sa.String(36), sa.ForeignKey("studios.id"), nullable=False),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("submitted_by", sa.String(100), nullable=False),
        sa.Column("handled_by", sa.String(100), nullable=True),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("category IN ('bug','question','request','other')", name="ck_feedback_category"),
        sa.CheckConstraint("status IN ('open','in_progress','resolved','rejected')", name="ck_feedback_status"),
    )
    op.create_index("ix_feedback_studio_created", "customer_feedback", ["studio_id", "created_at"])
    op.create_table(
        "feedback_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("feedback_id", sa.String(36), sa.ForeignKey("customer_feedback.id"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_actions_feedback_created", "feedback_actions", ["feedback_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_feedback_actions_feedback_created", table_name="feedback_actions")
    op.drop_table("feedback_actions")
    op.drop_index("ix_feedback_studio_created", table_name="customer_feedback")
    op.drop_table("customer_feedback")
