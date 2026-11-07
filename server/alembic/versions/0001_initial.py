"""Initial backend tables.

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa

from app.db.types import UTCDateTime

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("studio_id", sa.String(36), sa.ForeignKey("studios.id"), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_orders_period_month"),
        sa.CheckConstraint("price_cents >= 0", name="ck_orders_price_cents"),
        sa.CheckConstraint("status IN ('draft','awaiting_materials','ready_to_process','processing','awaiting_customer','awaiting_owner_review','approved','delivered','failed')", name="ck_orders_status"),
    )
    op.create_index("ix_orders_studio_created", "orders", ["studio_id", "created_at"])
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("file_kind", sa.String(32), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source_archive_id", sa.String(36), sa.ForeignKey("uploaded_files.id"), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("storage_key", name="uq_uploaded_files_storage_key"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_uploaded_files_size_bytes"),
    )
    op.create_index("ix_uploaded_files_order", "uploaded_files", ["order_id"])
    op.create_index("ix_uploaded_files_sha256", "uploaded_files", ["sha256"])
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("started_at", UTCDateTime(), nullable=True),
        sa.Column("ended_at", UTCDateTime(), nullable=True),
        sa.CheckConstraint("status IN ('queued','running','paused','succeeded','failed')", name="ck_agent_runs_status"),
    )
    op.create_index("ix_agent_runs_order_created", "agent_runs", ["order_id", "created_at"])
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("task_key", sa.String(100), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("started_at", UTCDateTime(), nullable=True),
        sa.Column("ended_at", UTCDateTime(), nullable=True),
        sa.UniqueConstraint("run_id", "task_key", name="uq_agent_tasks_run_task_key"),
        sa.CheckConstraint("status IN ('queued','running','paused','succeeded','failed')", name="ck_agent_tasks_status"),
    )
    op.create_index("ix_agent_tasks_order_status", "agent_tasks", ["order_id", "status"])
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("agent_tasks.id"), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_workflow_events_order_id", "workflow_events", ["order_id", "id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_audit_logs_order_created", "audit_logs", ["order_id", "created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("workflow_events")
    op.drop_table("agent_tasks")
    op.drop_table("agent_runs")
    op.drop_table("uploaded_files")
    op.drop_table("orders")
    op.drop_table("studios")
