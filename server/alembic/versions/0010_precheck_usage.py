"""Track intake precheck usage without an arbitrary total request cap."""
from alembic import op
import sqlalchemy as sa

revision = '0010_precheck_usage'
down_revision = '0009_intakes'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('intake_jobs') as batch:
        batch.alter_column('request_limit', existing_type=sa.Integer(), nullable=True)
    op.execute("UPDATE intake_jobs SET request_limit=NULL WHERE kind='precheck'")


def downgrade():
    op.execute("UPDATE intake_jobs SET request_limit=CASE WHEN requests_used>12 THEN requests_used ELSE 12 END WHERE request_limit IS NULL")
    with op.batch_alter_table('intake_jobs') as batch:
        batch.alter_column('request_limit', existing_type=sa.Integer(), nullable=False)
