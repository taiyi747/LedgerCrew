"""Preserve linked MVP records and read APIs when an older schema is upgraded."""

import asyncio
import hashlib
import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_migration_safety import counts, seed_mvp

from alembic import command
from app.core.config import get_settings
from app.db.session import get_session, make_engine
from app.main import app
from app.models import (
    AgentRun,
    AgentTask,
    AuditLog,
    BankTransaction,
    ExceptionTicket,
    InvoiceRecord,
    Order,
    ReconciliationBatch,
    ReconciliationMatch,
    ReportVersion,
    StatementImport,
    Studio,
    UploadedFile,
    WorkflowEvent,
)
from app.storage.local import LocalStorage, get_storage

HISTORICAL_REVISION = "0007_delivery"
FILE_BYTES = b"synthetic-mvp-file"


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}


def _rows(connection: sqlite3.Connection, table: str, columns: list[str]) -> list[tuple]:
    names = ", ".join(f'"{name}"' for name in columns)
    return connection.execute(f'SELECT {names} FROM "{table}" ORDER BY id').fetchall()


@pytest.fixture
def upgraded_history(tmp_path: Path, monkeypatch) -> tuple[Path, Path, dict[str, tuple[list[str], list[tuple]]], str]:
    db_path = tmp_path / "mvp-history.sqlite3"
    storage_path = tmp_path / "storage"
    assert not db_path.exists()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("STORAGE_ROOT", str(storage_path))
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    command.upgrade(config, HISTORICAL_REVISION)

    LocalStorage(str(storage_path)).put("synthetic/file-1", FILE_BYTES)
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        seed_mvp(connection)
        connection.execute("UPDATE uploaded_files SET sha256=? WHERE id='file-1'", (hashlib.sha256(FILE_BYTES).hexdigest(),))
        connection.commit()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert all(value == 1 for value in counts(connection).values())
        before: dict[str, tuple[list[str], list[tuple]]] = {}
        for table in _tables(connection) - {"alembic_version"}:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            before[table] = (columns, _rows(connection, table, columns))

    command.upgrade(config, "head")
    yield db_path, storage_path, before, head
    get_settings.cache_clear()


def test_mvp_history_rows_keys_and_relations_survive_upgrade(upgraded_history) -> None:
    db_path, _, before, head = upgraded_history
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [(head,)]
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert set(before) <= _tables(connection)
        for table, (columns, original_rows) in before.items():
            assert _rows(connection, table, columns) == original_rows, table
        assert counts(connection) == {table: 1 for table in counts(connection)}
        assert connection.execute(
            "SELECT f.order_id,o.studio_id FROM uploaded_files f JOIN orders o ON o.id=f.order_id"
        ).fetchone() == ("order-1", "studio-1")
        assert connection.execute(
            "SELECT b.statement_import_id,s.uploaded_file_id FROM bank_transactions b "
            "JOIN statement_imports s ON s.id=b.statement_import_id"
        ).fetchone() == ("import-1", "file-1")
        assert connection.execute(
            "SELECT m.invoice_id,m.transaction_id,m.batch_id FROM reconciliation_matches m"
        ).fetchone() == ("invoice-1", "transaction-1", "batch-1")
        assert connection.execute(
            "SELECT t.run_id,e.task_id,r.source_task_id FROM agent_tasks t "
            "JOIN workflow_events e ON e.task_id=t.id JOIN report_versions r ON r.source_task_id=t.id"
        ).fetchone() == ("run-1", "task-1", "task-1")


def test_upgraded_history_is_readable_through_current_orm(upgraded_history) -> None:
    db_path, _, _, _ = upgraded_history

    async def check() -> None:
        engine = make_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                for model, row_id in (
                    (Studio, "studio-1"), (Order, "order-1"), (UploadedFile, "file-1"),
                    (StatementImport, "import-1"), (BankTransaction, "transaction-1"),
                    (InvoiceRecord, "invoice-1"), (ReconciliationBatch, "batch-1"),
                    (ReconciliationMatch, "match-1"), (ExceptionTicket, "exception-1"),
                    (AgentTask, "task-1"), (AgentRun, "run-1"), (ReportVersion, "report-1"),
                ):
                    assert await session.get(model, row_id) is not None, model.__name__
                assert len((await session.scalars(select(WorkflowEvent))).all()) == 1
                assert len((await session.scalars(select(AuditLog))).all()) == 1
                assert (await session.get(BankTransaction, "transaction-1")).amount_cents == 1000
                assert (await session.get(ReportVersion, "report-1")).version == 1
        finally:
            await engine.dispose()

    asyncio.run(check())


def test_mvp_read_api_and_tenant_isolation_after_upgrade(upgraded_history) -> None:
    db_path, storage_path, _, _ = upgraded_history

    async def check() -> None:
        engine = make_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def test_session():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_session] = test_session
        app.dependency_overrides[get_storage] = lambda: LocalStorage(str(storage_path))
        alice = {"X-User-Id": "alice"}
        bob = {"X-User-Id": "bob"}
        owner = {"X-User-Id": "owner"}
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                for path, identifier in (
                    ("/api/v1/studios/studio-1", "studio-1"),
                    ("/api/v1/orders/order-1", "order-1"),
                    ("/api/v1/files/file-1", "file-1"),
                    ("/api/v1/imports/import-1", "import-1"),
                    ("/api/v1/exceptions/exception-1", "exception-1"),
                ):
                    response = await client.get(path, headers=alice)
                    assert response.status_code == 200, (path, response.text)
                    assert response.json()["id"] == identifier
                    assert (await client.get(path, headers=bob)).status_code == 404
                for path, identifier in (
                    ("/api/v1/orders/order-1/files", "file-1"),
                    ("/api/v1/orders/order-1/transactions", "transaction-1"),
                    ("/api/v1/orders/order-1/matches", "match-1"),
                    ("/api/v1/orders/order-1/exceptions", "exception-1"),
                ):
                    response = await client.get(path, headers=alice)
                    assert response.status_code == 200, (path, response.text)
                    assert [item["id"] for item in response.json()] == [identifier]
                reconciliation = await client.get("/api/v1/orders/order-1/reconciliation", headers=alice)
                assert reconciliation.status_code == 200, reconciliation.text
                assert reconciliation.json()["id"] == "batch-1"
                assert reconciliation.json()["income_total_cents"] == 1000
                downloaded = await client.get("/api/v1/files/file-1/download", headers=alice)
                assert downloaded.status_code == 200 and downloaded.content == FILE_BYTES
                reports = await client.get("/api/v1/orders/order-1/reports", headers=owner)
                assert reports.status_code == 200 and [row["id"] for row in reports.json()] == ["report-1"]
                report = await client.get("/api/v1/reports/report-1", headers=owner)
                assert report.status_code == 200 and report.json()["version"] == 1
                assert (await client.get("/api/v1/reports/report-1", headers=alice)).status_code == 404
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(check())
