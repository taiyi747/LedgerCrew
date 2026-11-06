from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401 -- register metadata

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def sync_url() -> str:
    url = get_settings().database_url
    if not url.startswith("sqlite+aiosqlite:///"):
        raise ValueError("Only SQLite with aiosqlite is supported")
    return url.replace("sqlite+aiosqlite://", "sqlite://", 1)


def run_migrations_offline() -> None:
    context.configure(url=sync_url(), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine: Engine = create_engine(sync_url())

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
