"""Track source files for Agent-normalized material outputs."""
from alembic import op
import sqlalchemy as sa

revision = "0011_material_workspace"
down_revision = "0010_precheck_usage"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("intake_files") as batch:
        batch.add_column(sa.Column("derived_from_file_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("derivation_key", sa.String(128), nullable=True))
        batch.create_foreign_key("fk_intake_file_derived_source", "intake_files", ["derived_from_file_id"], ["id"])
        batch.create_unique_constraint("uq_intake_file_derivation", ["derivation_key"])


def downgrade():
    with op.batch_alter_table("intake_files") as batch:
        batch.drop_constraint("uq_intake_file_derivation", type_="unique")
        batch.drop_constraint("fk_intake_file_derived_source", type_="foreignkey")
        batch.drop_column("derivation_key")
        batch.drop_column("derived_from_file_id")
