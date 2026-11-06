"""Customer supplements, owner decisions, and versioned reports.

Revision ID: 0007_delivery
Revises: 0006_agent_integration
"""

from alembic import op
import sqlalchemy as sa

from app.db.types import UTCDateTime

revision = "0007_delivery"
down_revision = "0006_agent_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exception_tickets", sa.Column("business_classification", sa.String(100), nullable=True))
    op.create_table(
        "exception_supplements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("exception_id", sa.String(36), sa.ForeignKey("exception_tickets.id"), nullable=False),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("uploaded_files.id"), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("explanation IS NOT NULL OR file_id IS NOT NULL", name="ck_exception_supplement_content"),
    )
    op.create_index("ix_exception_supplements_exception_created", "exception_supplements", ["exception_id", "created_at"])
    op.create_table(
        "exception_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("exception_id", sa.String(36), sa.ForeignKey("exception_tickets.id"), nullable=False),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("target_version", sa.Integer(), nullable=False),
        sa.Column("classification_before", sa.String(100), nullable=True),
        sa.Column("classification_after", sa.String(100), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("decision IN ('resolve','request_supplement','reanalyze','correct_classification','accept_unresolved')", name="ck_exception_decision_type"),
        sa.CheckConstraint("target_version > 0", name="ck_exception_decision_target_version"),
    )
    op.create_index("ix_exception_decisions_exception_created", "exception_decisions", ["exception_id", "created_at"])
    op.create_table(
        "report_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_task_id", sa.String(36), sa.ForeignKey("agent_tasks.id"), nullable=True),
        sa.Column("reconciliation_batch_id", sa.String(36), sa.ForeignKey("reconciliation_batches.id"), nullable=False),
        sa.Column("report_content", sa.Text(), nullable=False),
        sa.Column("financial_summary", sa.JSON(), nullable=False),
        sa.Column("reconciliation_summary", sa.JSON(), nullable=False),
        sa.Column("exception_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("unresolved_items", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("approved_at", UTCDateTime(), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("published_at", UTCDateTime(), nullable=True),
        sa.UniqueConstraint("order_id", "version", name="uq_report_versions_order_version"),
        sa.UniqueConstraint("source_task_id", name="uq_report_versions_source_task"),
        sa.CheckConstraint("version > 0", name="ck_report_version_positive"),
        sa.CheckConstraint("status IN ('draft','in_review','approved','published','superseded')", name="ck_report_version_status"),
    )
    op.create_index("ix_report_versions_order_status", "report_versions", ["order_id", "status"])
    op.create_table(
        "report_review_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("report_versions.id"), nullable=False),
        sa.Column("report_version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("action IN ('approved','rejected')", name="ck_report_review_action"),
    )
    op.create_index("ix_report_review_actions_report_created", "report_review_actions", ["report_id", "created_at"])


def downgrade() -> None:
    op.drop_table("report_review_actions")
    op.drop_table("report_versions")
    op.drop_table("exception_decisions")
    op.drop_table("exception_supplements")
    with op.batch_alter_table("exception_tickets") as batch_op:
        batch_op.drop_column("business_classification")
