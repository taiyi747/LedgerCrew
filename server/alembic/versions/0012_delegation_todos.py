"""Each specialist Agent plans its own todo list for a delegation."""
from alembic import op
import sqlalchemy as sa

revision = "0012_delegation_todos"
down_revision = "0011_material_workspace"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("workflow_delegations") as batch:
        batch.add_column(sa.Column("todos", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    with op.batch_alter_table("workflow_delegations") as batch:
        batch.drop_column("todos")
