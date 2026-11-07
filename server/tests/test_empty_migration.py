"""Independent empty SQLite database to Alembic head regression tests."""

import asyncio
import sqlite3
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import UniqueConstraint, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models  # noqa: F401 -- register every mapped table
from alembic import command
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import make_engine
from app.models import Order, Studio, UploadedFile


@pytest.fixture
def empty_migrated_database(tmp_path: Path, monkeypatch) -> tuple[Path, str]:
    db_path = tmp_path / "empty-to-head.sqlite3"
    assert not db_path.exists()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    assert len(heads) == 1
    revisions = list(reversed(list(scripts.walk_revisions(base="base", head="heads"))))
    assert revisions and revisions[0].down_revision is None
    for previous, current in pairwise(revisions):
        assert current.down_revision == previous.revision
    assert revisions[-1].revision == heads[0]
    command.upgrade(config, "head")
    assert db_path.is_file()
    yield db_path, heads[0]
    get_settings.cache_clear()


def test_empty_upgrade_revision_and_metadata(empty_migrated_database: tuple[Path, str]) -> None:
    db_path, head = empty_migrated_database
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [(head,)]
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        schema = inspect(engine)
        assert set(schema.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        for model_table in Base.metadata.tables.values():
            table_name = model_table.name
            actual_columns = {column["name"]: column for column in schema.get_columns(table_name)}
            assert set(actual_columns) == {column.name for column in model_table.columns}, table_name
            assert schema.get_pk_constraint(table_name)["constrained_columns"] == [
                column.name for column in model_table.primary_key.columns
            ], table_name
            for column in model_table.columns:
                assert actual_columns[column.name]["nullable"] == column.nullable, (table_name, column.name)
                if column.server_default is not None:
                    assert actual_columns[column.name]["default"] is not None, (table_name, column.name)

            if table_name == "agent_tasks":
                assert str(actual_columns["attempt_count"]["default"]).strip("'\"()") == "0"

            expected_fks = {(fk.parent.name, fk.column.table.name, fk.column.name)
                            for column in model_table.columns for fk in column.foreign_keys}
            actual_fks = {(local, fk["referred_table"], remote)
                          for fk in schema.get_foreign_keys(table_name)
                          for local, remote in zip(fk["constrained_columns"], fk["referred_columns"], strict=True)}
            assert actual_fks == expected_fks, table_name
            assert {index.name for index in model_table.indexes} == {
                index["name"] for index in schema.get_indexes(table_name)
            }, table_name
            assert {constraint.name for constraint in model_table.constraints
                    if isinstance(constraint, UniqueConstraint)} == {
                constraint["name"] for constraint in schema.get_unique_constraints(table_name)
            }, table_name
    finally:
        engine.dispose()


def test_application_sqlite_connection_enforces_foreign_keys_and_required_fields(
    empty_migrated_database: tuple[Path, str],
) -> None:
    db_path, _ = empty_migrated_database

    async def check() -> None:
        engine = make_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        try:
            async with engine.connect() as connection:
                assert (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one() == 1
                with pytest.raises(IntegrityError):
                    await connection.execute(text("""
                        INSERT INTO uploaded_files
                        (id, order_id, original_filename, storage_key, file_category, mime_type,
                         file_size, sha256, upload_source, validation_status, created_at)
                        VALUES
                        ('orphan', 'missing-order', 'test.png', 'orphan-key', 'invoice_image',
                         'image/png', 1, :hash, 'manual', 'valid', :now)
                    """), {"hash": "a" * 64, "now": "2026-11-07T00:00:00+00:00"})
                await connection.rollback()
                with pytest.raises(IntegrityError):
                    await connection.execute(text("""
                        INSERT INTO studios (id, created_at, updated_at)
                        VALUES ('missing-name', :now, :now)
                    """), {"now": "2026-11-07T00:00:00+00:00"})
                await connection.rollback()
        finally:
            await engine.dispose()

    asyncio.run(check())


def test_orm_write_read_unique_constraints_and_server_default(
    empty_migrated_database: tuple[Path, str],
) -> None:
    db_path, _ = empty_migrated_database

    async def check() -> tuple[str, str, str]:
        engine = make_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                studio = Studio(name="Synthetic studio", owner_user_id="synthetic-user")
                session.add(studio)
                await session.flush()
                order = Order(
                    studio_id=studio.id, order_no="LC-empty-migration", period_start=date(2026, 10, 1),
                    period_end=date(2026, 10, 31), period_year=2026, period_month=10, price_cents=1990,
                )
                session.add(order)
                await session.flush()
                uploaded = UploadedFile(
                    order_id=order.id, original_filename="synthetic.png", storage_key="synthetic/file",
                    file_category="invoice_image", mime_type="image/png", file_size=1, sha256="b" * 64,
                    upload_source="manual", validation_status="valid",
                )
                session.add(uploaded)
                await session.commit()
                studio_id, order_id, file_id = studio.id, order.id, uploaded.id

            async with sessions() as session:
                stored_studio = await session.get(Studio, studio_id)
                stored_order = await session.get(Order, order_id)
                stored_file = await session.get(UploadedFile, file_id)
                assert stored_studio is not None and stored_studio.name == "Synthetic studio"
                assert stored_order is not None and stored_order.studio_id == studio_id
                assert stored_order.status == "draft" and stored_order.is_simulated is True
                assert stored_order.created_at.utcoffset() == timedelta(0)
                assert stored_file is not None and stored_file.order_id == order_id
                assert stored_file.storage_key == "synthetic/file"

            async with sessions() as session:
                with pytest.raises(IntegrityError):
                    session.add(Order(
                        studio_id=studio_id, order_no="LC-empty-migration", period_start=date(2026, 10, 1),
                        period_end=date(2026, 10, 31), period_year=2026, period_month=10, price_cents=1990,
                    ))
                    await session.commit()
            async with sessions() as session:
                with pytest.raises(IntegrityError):
                    session.add(UploadedFile(
                        order_id=order_id, original_filename="other.png", storage_key="synthetic/file",
                        file_category="invoice_image", mime_type="image/png", file_size=1, sha256="c" * 64,
                        upload_source="manual", validation_status="valid",
                    ))
                    await session.commit()
            return studio_id, order_id, file_id
        finally:
            await engine.dispose()

    studio_id, order_id, file_id = asyncio.run(check())
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("""
            INSERT INTO orders
            (id, studio_id, order_no, period_start, period_end, period_year, period_month,
             status, price_cents, created_at, updated_at)
            VALUES ('server-default-order', ?, 'LC-server-default', '2026-11-01', '2026-11-30',
                    2026, 11, 'draft', 1990, '2026-11-07T00:00:00+00:00', '2026-11-07T00:00:00+00:00')
        """, (studio_id,))
        assert connection.execute(
            "SELECT is_simulated FROM orders WHERE id='server-default-order'"
        ).fetchone() == (1,)
        assert connection.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone() == (order_id,)
        assert connection.execute("SELECT id FROM uploaded_files WHERE id=?", (file_id,)).fetchone() == (file_id,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
