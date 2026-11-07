"""Sandbox payment intent, event and reconciliation records.

Revision ID: 0010_sandbox_payments
Revises: 0009_local_identity
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_sandbox_payments"
down_revision = "0009_local_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("currency", sa.String(3), nullable=True))
    op.create_table(
        "payment_intents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_ref", sa.String(100), nullable=False, unique=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("refunded_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("order_id", "idempotency_key", name="uq_payment_order_idempotency"),
        sa.CheckConstraint("amount_cents > 0", name="ck_payment_positive_amount"),
        sa.CheckConstraint("refunded_cents >= 0 AND refunded_cents <= amount_cents", name="ck_payment_refunded_range"),
        sa.CheckConstraint("status IN ('pending','succeeded','failed','cancelled','partially_refunded','refunded')",
                           name="ck_payment_status"),
    )
    op.create_index("ix_payment_intents_order_status", "payment_intents", ["order_id", "status"])
    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("intent_id", sa.String(36), sa.ForeignKey("payment_intents.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_payment_provider_event"),
    )
    op.create_table(
        "payment_reconciliations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("intent_id", sa.String(36), sa.ForeignKey("payment_intents.id"), nullable=False),
        sa.Column("expected_status", sa.String(32), nullable=False),
        sa.Column("observed_status", sa.String(32), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("payment_reconciliations")
    op.drop_table("payment_events")
    op.drop_index("ix_payment_intents_order_status", table_name="payment_intents")
    op.drop_table("payment_intents")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("currency")
