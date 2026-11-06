"""Require order number and period dates.

Revision ID: 0003_required_order_fields
Revises: 0002_studios_orders_files
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_required_order_fields"
down_revision = "0002_studios_orders_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.alter_column("order_no", existing_type=sa.String(40), nullable=False)
        batch.alter_column("period_start", existing_type=sa.Date(), nullable=False)
        batch.alter_column("period_end", existing_type=sa.Date(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.alter_column("period_end", existing_type=sa.Date(), nullable=True)
        batch.alter_column("period_start", existing_type=sa.Date(), nullable=True)
        batch.alter_column("order_no", existing_type=sa.String(40), nullable=True)
