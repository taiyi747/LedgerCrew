import asyncio
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

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
    db_path = tmp_path / f"test-{uuid4().hex}.db"
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
        assert {"studios", "orders", "uploaded_files", "agent_runs", "agent_tasks", "workflow_events", "audit_logs", "alembic_version", "invoice_records", "reconciliation_batches", "reconciliation_matches", "exception_tickets", "exception_supplements", "exception_decisions", "report_versions", "report_review_actions"} <= names
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0008_live_workflow"
        task_columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_tasks)")}
        assert {"idempotency_key", "correlation_id", "input_schema_version", "provider_metadata", "attempt_count"} <= task_columns
        run_columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_runs)")}
        assert {"checkpoint_data", "correlation_id", "input_schema_version"} <= run_columns


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
                order = Order(order_no="LC-test-order", studio_id=studio.id, period_start=date(2026, 11, 1), period_end=date(2026, 11, 30), period_year=2026, period_month=11, price_cents=1990)
                session.add(order)
                await session.commit()
                await session.refresh(order)
                assert order.status == "draft"
                assert order.created_at.utcoffset() == timedelta(0)
                assert order.created_at <= datetime.now(timezone.utc)
        finally:
            await engine.dispose()

    asyncio.run(check())


def test_upgrade_preserves_existing_order_and_file(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / f"legacy-{uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0001_initial")
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO studios(id,name,created_at,updated_at) VALUES ('studio-1','Legacy','2026-10-01','2026-10-01')")
        connection.execute("INSERT INTO orders(id,studio_id,period_year,period_month,status,price_cents,created_at,updated_at) VALUES ('order-1','studio-1',2026,10,'draft',1990,'2026-10-01','2026-10-01')")
        connection.execute("INSERT INTO uploaded_files(id,order_id,original_name,storage_key,file_kind,content_type,size_bytes,sha256,created_at) VALUES ('file-1','order-1','old.png','old-key','invoice_image','image/png',1,'abc','2026-10-01')")
        connection.commit()
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT period_start,period_end,price_cents,is_simulated FROM orders WHERE id='order-1'").fetchone()
        assert row == ("2026-10-01", "2026-10-31", 1990, 1)
        file_row = connection.execute("SELECT original_filename,file_category,file_size,validation_status FROM uploaded_files WHERE id='file-1'").fetchone()
        assert file_row == ("old.png", "invoice_image", 1, "pending_review")
