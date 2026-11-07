"""Durable supervisor delegation, artifacts, messages and input revisions."""
from alembic import op
import sqlalchemy as sa

revision = "0008_live_workflow"
down_revision = "0007_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("workflow_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(100), nullable=False), sa.Column("input_revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False), sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("requests_used", sa.Integer(), nullable=False), sa.Column("request_limit", sa.Integer(), nullable=False),
        sa.Column("wait_reason", sa.String(50)), sa.Column("error", sa.Text()),
        sa.Column("lease_token", sa.String(36)), sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)), sa.Column("checkpoint_id", sa.String(100)),
        sa.Column("pending_request_id", sa.String(100)), sa.Column("source_message_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", "idempotency_key", name="uq_workflow_request"),
        sa.CheckConstraint("requests_used >= 0 AND request_limit > 0", name="ck_workflow_budget"))
    op.create_index("ix_workflow_queue", "workflow_runs", ["status", "kind", "created_at"])
    op.create_index("uq_workflow_active_order", "workflow_runs", ["order_id"], unique=True,
                    sqlite_where=sa.text("kind = 'processing' AND status IN ('queued','running','paused')"))
    op.create_table("workflow_delegations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_run_id", sa.String(36), sa.ForeignKey("workflow_runs.id"), nullable=False),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("decision_id", sa.String(36), nullable=False), sa.Column("agent_role", sa.String(50), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False), sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("input_refs", sa.JSON(), nullable=False), sa.Column("input_revision", sa.Integer(), nullable=False),
        sa.Column("operation_key", sa.String(100), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("task_id", sa.String(36)), sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON()), sa.Column("receipts", sa.JSON(), nullable=False), sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workflow_run_id", "operation_key", name="uq_delegation_operation"))
    op.create_table("workflow_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_run_id", sa.String(36), sa.ForeignKey("workflow_runs.id"), nullable=False),
        sa.Column("kind", sa.String(100), nullable=False), sa.Column("operation_key", sa.String(100), nullable=False),
        sa.Column("input_revision", sa.Integer(), nullable=False), sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workflow_run_id", "operation_key", name="uq_workflow_artifact_operation"))
    op.create_table("order_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("workflow_run_id", sa.String(36), sa.ForeignKey("workflow_runs.id")),
        sa.Column("client_message_id", sa.String(100)), sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False), sa.Column("file_ids", sa.JSON(), nullable=False),
        sa.Column("input_revision", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", "client_message_id", name="uq_order_message_client"))
    op.add_column("orders", sa.Column("input_revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("uploaded_files", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("uploaded_files", sa.Column("replaced_by_file_id", sa.String(36), nullable=True))
    # Legacy published reports remain history; new drafts get an explicit revision.
    op.add_column("report_versions", sa.Column("source_revision", sa.Integer(), nullable=True))
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("workflow_run_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_agent_run_workflow", "workflow_runs", ["workflow_run_id"], ["id"])
    with op.batch_alter_table("agent_tasks") as batch:
        batch.add_column(sa.Column("workflow_run_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("delegation_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("source_revision", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_agent_task_workflow", "workflow_runs", ["workflow_run_id"], ["id"])
        batch.create_foreign_key("fk_agent_task_delegation", "workflow_delegations", ["delegation_id"], ["id"])


def downgrade():
    with op.batch_alter_table("agent_tasks") as batch:
        batch.drop_constraint("fk_agent_task_delegation", type_="foreignkey")
        batch.drop_constraint("fk_agent_task_workflow", type_="foreignkey")
        batch.drop_column("source_revision")
        batch.drop_column("delegation_id")
        batch.drop_column("workflow_run_id")
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_constraint("fk_agent_run_workflow", type_="foreignkey")
        batch.drop_column("workflow_run_id")
    op.drop_column("report_versions", "source_revision")
    op.drop_column("uploaded_files", "replaced_by_file_id")
    op.drop_column("uploaded_files", "is_active")
    op.drop_column("orders", "input_revision")
    for name in ["order_messages", "workflow_artifacts", "workflow_delegations", "workflow_runs"]:
        op.drop_table(name)
