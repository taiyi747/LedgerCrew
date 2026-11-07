"""MVP migration and SQLite backup checks on isolated synthetic databases.

There are no v0.2 migrations yet. These checks establish the baseline that a
future BE2 migration must preserve; they do not certify v0.2 rollback.
"""

import json
import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import UniqueConstraint, create_engine, inspect

import app.models  # noqa: F401 -- populate SQLAlchemy metadata
from alembic import command
from app.core.config import get_settings
from app.db.base import Base
from scripts.sqlite_snapshot import backup_database, restore_database

MVP_HEAD = "0008_invoice_provenance"
PREVIOUS_REVISION = "0007_delivery"
WHEN = "2026-11-07T00:00:00+00:00"


def migration_config(tmp_path: Path, monkeypatch) -> tuple[Config, Path]:
    db_path = tmp_path / "migration-check.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    return Config(str(Path(__file__).parents[1] / "alembic.ini")), db_path


def insert(connection: sqlite3.Connection, table: str, **values: object) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def seed_mvp(connection: sqlite3.Connection) -> None:
    """One linked row from every principal MVP domain at revision 0007."""
    insert(connection, "studios", id="studio-1", name="Synthetic", owner_user_id="alice", created_at=WHEN, updated_at=WHEN)
    insert(connection, "orders", id="order-1", studio_id="studio-1", order_no="LC-synthetic",
           period_start="2026-10-01", period_end="2026-10-31", period_year=2026, period_month=10,
           status="draft", price_cents=1990, is_simulated=1, created_at=WHEN, updated_at=WHEN)
    insert(connection, "uploaded_files", id="file-1", order_id="order-1", original_filename="synthetic.png",
           storage_key="synthetic/file-1", file_category="invoice_image", mime_type="image/png",
           file_size=1, sha256="a" * 64, upload_source="manual", validation_status="valid", created_at=WHEN)
    insert(connection, "statement_imports", id="import-1", order_id="order-1", uploaded_file_id="file-1",
           status="parsed", total_rows=1, success_rows=1, failed_rows=0, column_map_json="{}", created_at=WHEN)
    insert(connection, "bank_transactions", id="transaction-1", order_id="order-1", statement_import_id="import-1",
           row_number=1, external_id="synthetic-1", transaction_date="2026-10-15", counterparty="Synthetic",
           normalized_counterparty="synthetic", direction="IN", amount_cents=1000,
           raw_row_json='{"amount":"10.00"}', created_at=WHEN)
    insert(connection, "agent_runs", id="run-1", order_id="order-1", agent_name="synthetic", task_type="review",
           status="succeeded", created_at=WHEN)
    insert(connection, "agent_tasks", id="task-1", order_id="order-1", run_id="run-1", task_key="review-1",
           agent_name="synthetic", task_type="review", status="succeeded", created_at=WHEN)
    insert(connection, "workflow_events", order_id="order-1", run_id="run-1", task_id="task-1",
           event_type="synthetic.completed", payload="{}", created_at=WHEN)
    insert(connection, "invoice_records", id="invoice-1", order_id="order-1", source_file_id="file-1",
           invoice_number="SYN-1", issue_date="2026-10-15", amount_cents=1000, tax_cents=0,
           total_amount_cents=1000, extraction_status="ready", created_at=WHEN)
    insert(connection, "reconciliation_batches", id="batch-1", order_id="order-1", batch_number=1,
           income_total_cents=1000, expense_total_cents=0, net_cash_change_cents=1000,
           matched_count=1, unmatched_count=0, exception_count=1, created_at=WHEN)
    insert(connection, "reconciliation_matches", id="match-1", order_id="order-1", batch_id="batch-1",
           invoice_id="invoice-1", transaction_id="transaction-1", match_status="matched", difference_cents=0,
           match_rule="synthetic", evidence_json="{}", created_at=WHEN)
    insert(connection, "exception_tickets", id="exception-1", exception_no="EX-synthetic", order_id="order-1",
           batch_id="batch-1", exception_type="MISSING_INVOICE", transaction_id="transaction-1",
           status="open", evidence_json="{}", created_at=WHEN, updated_at=WHEN)
    insert(connection, "report_versions", id="report-1", order_id="order-1", version=1, status="draft",
           source_task_id="task-1", reconciliation_batch_id="batch-1", report_content="Synthetic report",
           financial_summary="{}", reconciliation_summary="{}", exception_snapshot="[]",
           evidence_references="[]", unresolved_items="[]", content_hash="b" * 64, created_at=WHEN)
    insert(connection, "audit_logs", order_id="order-1", actor_type="system", action="synthetic.seed",
           entity_type="order", entity_id="order-1", details="{}", created_at=WHEN)


def counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "studios", "orders", "uploaded_files", "statement_imports", "bank_transactions",
        "agent_runs", "agent_tasks", "workflow_events", "invoice_records",
        "reconciliation_batches", "reconciliation_matches", "exception_tickets",
        "report_versions", "audit_logs",
    )
    return {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in tables}


def test_empty_upgrade_matches_mvp_metadata(tmp_path, monkeypatch) -> None:
    config, db_path = migration_config(tmp_path, monkeypatch)
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == [MVP_HEAD]
    revisions = list(scripts.walk_revisions(base="base", head="heads"))
    assert len(revisions) == 8
    assert revisions[-1].revision == "0001_initial"

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        schema = inspect(engine)
        assert set(schema.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        for table in Base.metadata.tables.values():
            actual_columns = {column["name"]: column for column in schema.get_columns(table.name)}
            assert set(actual_columns) == {column.name for column in table.columns}, table.name
            for column in table.columns:
                assert actual_columns[column.name]["nullable"] == column.nullable, (table.name, column.name)
            expected_fks = {(fk.parent.name, fk.column.table.name, fk.column.name)
                            for column in table.columns for fk in column.foreign_keys}
            actual_fks = {(local, fk["referred_table"], remote)
                          for fk in schema.get_foreign_keys(table.name)
                          for local, remote in zip(fk["constrained_columns"], fk["referred_columns"], strict=True)}
            assert actual_fks == expected_fks, table.name
            expected_indexes = {index.name for index in table.indexes}
            actual_indexes = {index["name"] for index in schema.get_indexes(table.name)}
            assert actual_indexes == expected_indexes, table.name
            expected_uniques = {constraint.name for constraint in table.constraints
                                if isinstance(constraint, UniqueConstraint)}
            actual_uniques = {constraint["name"] for constraint in schema.get_unique_constraints(table.name)}
            assert actual_uniques == expected_uniques, table.name
        with sqlite3.connect(db_path) as connection:
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        engine.dispose()


def test_mvp_upgrade_rollback_reupgrade_and_wal_backup(tmp_path, monkeypatch) -> None:
    config, db_path = migration_config(tmp_path, monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        seed_mvp(connection)
        connection.commit()
        baseline = counts(connection)
        assert all(value == 1 for value in baseline.values())
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        backup_path = tmp_path / "mvp-backup.db"
        manifest = backup_database(db_path, backup_path)
        assert manifest["revision"] == PREVIOUS_REVISION
        with sqlite3.connect(backup_path) as backup:
            assert counts(backup) == baseline
            assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert backup.execute("SELECT version_num FROM alembic_version").fetchone() == (PREVIOUS_REVISION,)

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert counts(connection) == baseline
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (MVP_HEAD,)
        assert connection.execute(
            "SELECT source_task_id, material_review_task_id FROM invoice_records WHERE id='invoice-1'"
        ).fetchone() == (None, None)

    # This only exercises the 0008 schema change. A populated provenance field
    # would be discarded by downgrade; no production rollback is implied.
    command.downgrade(config, PREVIOUS_REVISION)
    with sqlite3.connect(db_path) as connection:
        assert counts(connection) == baseline
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (PREVIOUS_REVISION,)
    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        assert counts(connection) == baseline
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    restored_path = tmp_path / "restored.db"
    assert restore_database(backup_path, restored_path)["revision"] == PREVIOUS_REVISION
    with sqlite3.connect(restored_path) as restored:
        assert counts(restored) == baseline
        assert restored.execute("PRAGMA foreign_key_check").fetchall() == []
        assert restored.execute("SELECT version_num FROM alembic_version").fetchone() == (PREVIOUS_REVISION,)


def test_backup_never_overwrites_and_rejects_tampered_manifest(tmp_path, monkeypatch) -> None:
    config, db_path = migration_config(tmp_path, monkeypatch)
    command.upgrade(config, "head")
    backup_path = tmp_path / "snapshot.db"
    backup_database(db_path, backup_path)
    with pytest.raises(FileExistsError):
        backup_database(db_path, backup_path)
    with pytest.raises(ValueError, match="Source and target must differ"):
        backup_database(db_path, db_path)

    valid_restore_path = tmp_path / "valid-restore.db"
    assert restore_database(backup_path, valid_restore_path)["revision"] == MVP_HEAD
    with pytest.raises(FileExistsError):
        restore_database(backup_path, valid_restore_path)

    manifest_path = tmp_path / "snapshot.db.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    restored_path = tmp_path / "should-not-exist.db"
    with pytest.raises(ValueError, match="manifest does not match"):
        restore_database(backup_path, restored_path)
    assert not restored_path.exists()
