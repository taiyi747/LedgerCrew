import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.db.session import make_engine
from app.main import app
from app.models import Order, Studio


def migrated_db(tmp_path: Path, monkeypatch) -> Path:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    return db_path


def test_app_starts_and_health_responds() -> None:
    async def check() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            assert (await client.get("/openapi.json")).status_code == 200
            assert (await client.get("/missing")).json() == {"error": {"code": "http_error", "message": "Not Found"}}

    asyncio.run(check())


def test_migration_creates_tables_and_constraints(tmp_path: Path, monkeypatch) -> None:
    db_path = migrated_db(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"studios", "orders", "uploaded_files", "agent_runs", "agent_tasks", "workflow_events", "audit_logs", "alembic_version"} <= names
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0001_initial"


def test_async_database_connection_and_utc_round_trip(tmp_path: Path, monkeypatch) -> None:
    db_path = migrated_db(tmp_path, monkeypatch)

    async def check() -> None:
        engine = make_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
                studio = Studio(name="Test Studio")
                session.add(studio)
                await session.flush()
                order = Order(studio_id=studio.id, period_year=2026, period_month=11, price_cents=1990)
                session.add(order)
                await session.commit()
                await session.refresh(order)
                assert order.status == "draft"
                assert order.created_at.utcoffset() == timedelta(0)
                assert order.created_at <= datetime.now(timezone.utc)
        finally:
            await engine.dispose()

    asyncio.run(check())
