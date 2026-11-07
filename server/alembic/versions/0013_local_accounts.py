"""Local accounts: users, cookie sessions and idempotent trial requests."""
from alembic import op
import sqlalchemy as sa

from app.db.types import UTCDateTime

revision = "0013_local_accounts"
down_revision = "0012_delegation_todos"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("username_key", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("username_key", name="uq_users_username_key"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("revoked_at", UTCDateTime(), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_user_created", "user_sessions", ["user_id", "created_at"])
    op.create_table(
        "trial_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("request_id", name="uq_trial_requests_request_id"),
    )
    op.create_index("ix_trial_requests_user", "trial_requests", ["user_id"])


def downgrade():
    op.drop_index("ix_trial_requests_user", table_name="trial_requests")
    op.drop_table("trial_requests")
    op.drop_index("ix_user_sessions_user_created", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
