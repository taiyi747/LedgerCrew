"""Studio ownership, order period, and upload metadata.

Revision ID: 0002_studios_orders_files
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_studios_orders_files"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("studios", sa.Column("business_type", sa.String(100), nullable=True))
    op.add_column("studios", sa.Column("owner_user_id", sa.String(100), nullable=True))
    op.create_index("ix_studios_owner", "studios", ["owner_user_id"])

    with op.batch_alter_table("orders") as batch:
        batch.add_column(sa.Column("order_no", sa.String(40), nullable=True))
        batch.add_column(sa.Column("period_start", sa.Date(), nullable=True))
        batch.add_column(sa.Column("period_end", sa.Date(), nullable=True))
        batch.add_column(sa.Column("service_scope", sa.String(200), nullable=True))
        batch.add_column(sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.alter_column("price_cents", existing_type=sa.Integer(), nullable=True)
        batch.create_unique_constraint("uq_orders_order_no", ["order_no"])
        batch.create_check_constraint("ck_orders_period_range", "period_end >= period_start")
    op.execute("UPDATE orders SET order_no = 'LC-' || id, period_start = printf('%04d-%02d-01', period_year, period_month), period_end = date(printf('%04d-%02d-01', period_year, period_month), '+1 month', '-1 day') WHERE order_no IS NULL")

    op.alter_column("uploaded_files", "original_name", new_column_name="original_filename", existing_type=sa.String(255))
    op.alter_column("uploaded_files", "file_kind", new_column_name="file_category", existing_type=sa.String(32))
    op.alter_column("uploaded_files", "content_type", new_column_name="mime_type", existing_type=sa.String(100))
    op.alter_column("uploaded_files", "size_bytes", new_column_name="file_size", existing_type=sa.Integer())
    op.alter_column("uploaded_files", "source_archive_id", new_column_name="archive_file_id", existing_type=sa.String(36))
    op.add_column("uploaded_files", sa.Column("upload_source", sa.String(16), nullable=False, server_default="legacy"))
    op.add_column("uploaded_files", sa.Column("validation_status", sa.String(16), nullable=False, server_default="pending_review"))
    op.add_column("uploaded_files", sa.Column("archive_entry_path", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("uploaded_files", "archive_entry_path")
    op.drop_column("uploaded_files", "validation_status")
    op.drop_column("uploaded_files", "upload_source")
    op.alter_column("uploaded_files", "archive_file_id", new_column_name="source_archive_id", existing_type=sa.String(36))
    op.alter_column("uploaded_files", "file_size", new_column_name="size_bytes", existing_type=sa.Integer())
    op.alter_column("uploaded_files", "mime_type", new_column_name="content_type", existing_type=sa.String(100))
    op.alter_column("uploaded_files", "file_category", new_column_name="file_kind", existing_type=sa.String(32))
    op.alter_column("uploaded_files", "original_filename", new_column_name="original_name", existing_type=sa.String(255))
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("ck_orders_period_range", type_="check")
        batch.drop_constraint("uq_orders_order_no", type_="unique")
        batch.alter_column("price_cents", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("is_simulated")
        batch.drop_column("service_scope")
        batch.drop_column("period_end")
        batch.drop_column("period_start")
        batch.drop_column("order_no")
    op.drop_index("ix_studios_owner", table_name="studios")
    op.drop_column("studios", "owner_user_id")
    op.drop_column("studios", "business_type")
