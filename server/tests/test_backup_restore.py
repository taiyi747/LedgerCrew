"""SQLite backup, WAL, restore failure, and lossy MVP downgrade checks."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from test_migration_safety import MVP_HEAD, PREVIOUS_REVISION, WHEN, counts, seed_mvp

from alembic import command
from app.core.config import get_settings
from scripts.sqlite_snapshot import backup_database, inspect_database, restore_database


def _database(tmp_path: Path, monkeypatch, revision: str) -> tuple[Config, Path]:
    db_path = tmp_path / "isolated-backup-test.db"
    assert not db_path.exists()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, revision)
    return config, db_path


def test_wal_backup_includes_committed_uncheckpointed_rows_and_restores(tmp_path, monkeypatch) -> None:
    _, db_path = _database(tmp_path, monkeypatch, "head")
    with closing(sqlite3.connect(db_path)) as writer:
        writer.execute("PRAGMA foreign_keys=ON")
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        seed_mvp(writer)
        writer.commit()
        with closing(sqlite3.connect(db_path)) as reader:
            reader.execute("BEGIN")
            assert reader.execute("SELECT count(*) FROM audit_logs").fetchone() == (1,)
            writer.execute(
                "INSERT INTO audit_logs (order_id,actor_type,action,entity_type,entity_id,created_at) "
                "VALUES ('order-1','system','wal.commit','order','order-1',?)",
                (WHEN,),
            )
            writer.commit()
            assert Path(f"{db_path}-wal").stat().st_size > 0
            backup_path = tmp_path / "wal-snapshot.db"
            manifest = backup_database(db_path, backup_path)

    assert manifest["revision"] == MVP_HEAD
    assert datetime.fromisoformat(manifest["backup_time_utc"].replace("Z", "+00:00")).utcoffset() == timedelta(0)
    assert manifest["sha256"] == hashlib.sha256(backup_path.read_bytes()).hexdigest()
    assert json.loads((tmp_path / "wal-snapshot.db.manifest.json").read_text(encoding="utf-8")) == manifest
    with closing(sqlite3.connect(backup_path)) as backup:
        assert backup.execute("SELECT count(*) FROM audit_logs").fetchone() == (2,)
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert backup.execute("PRAGMA foreign_key_check").fetchall() == []

    restored_path = tmp_path / "restored-wal.db"
    assert restore_database(backup_path, restored_path)["revision"] == MVP_HEAD
    with closing(sqlite3.connect(restored_path)) as restored:
        assert restored.execute("SELECT count(*) FROM audit_logs").fetchone() == (2,)
        assert counts(restored)["orders"] == 1
        assert restored.execute("SELECT version_num FROM alembic_version").fetchone() == (MVP_HEAD,)
        assert restored.execute("PRAGMA foreign_key_check").fetchall() == []


def test_downgrade_loses_new_provenance_but_backup_restores_it(tmp_path, monkeypatch) -> None:
    config, db_path = _database(tmp_path, monkeypatch, PREVIOUS_REVISION)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        seed_mvp(connection)
        connection.commit()
    command.upgrade(config, "head")
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "UPDATE invoice_records SET source_task_id='task-1', material_review_task_id='task-1' "
            "WHERE id='invoice-1'"
        )
        connection.execute(
            "INSERT INTO audit_logs (order_id,actor_type,action,entity_type,entity_id,created_at) "
            "VALUES ('order-1','system','after.upgrade','invoice_record','invoice-1',?)",
            (WHEN,),
        )
        connection.commit()
        baseline = counts(connection)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT source_task_id,material_review_task_id FROM invoice_records WHERE id='invoice-1'"
        ).fetchone() == ("task-1", "task-1")
    backup_path = tmp_path / "before-downgrade.db"
    assert backup_database(db_path, backup_path)["revision"] == MVP_HEAD

    command.downgrade(config, PREVIOUS_REVISION)
    with closing(sqlite3.connect(db_path)) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (PREVIOUS_REVISION,)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(invoice_records)")}
        assert "source_task_id" not in columns and "material_review_task_id" not in columns
        assert counts(connection) == baseline
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    command.upgrade(config, "head")
    with closing(sqlite3.connect(db_path)) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (MVP_HEAD,)
        assert counts(connection) == baseline
        assert connection.execute(
            "SELECT source_task_id,material_review_task_id FROM invoice_records WHERE id='invoice-1'"
        ).fetchone() == (None, None)

    recovered_path = tmp_path / "recovered-with-provenance.db"
    assert restore_database(backup_path, recovered_path)["revision"] == MVP_HEAD
    with closing(sqlite3.connect(recovered_path)) as recovered:
        assert counts(recovered) == baseline
        assert recovered.execute(
            "SELECT source_task_id,material_review_task_id FROM invoice_records WHERE id='invoice-1'"
        ).fetchone() == ("task-1", "task-1")
        assert recovered.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert recovered.execute("PRAGMA foreign_key_check").fetchall() == []


def test_corruption_manifest_and_wrong_restore_targets_are_rejected(tmp_path, monkeypatch) -> None:
    _, db_path = _database(tmp_path, monkeypatch, "head")
    backup_path = tmp_path / "valid-snapshot.db"
    backup_database(db_path, backup_path)

    damaged_path = tmp_path / "damaged-snapshot.db"
    damaged_path.write_bytes(b"not a SQLite database")
    invalid_target = tmp_path / "must-not-exist.db"
    with pytest.raises(ValueError, match="cannot be validated"):
        restore_database(damaged_path, invalid_target)
    assert not invalid_target.exists()
    with pytest.raises(ValueError, match="Target directory does not exist"):
        restore_database(backup_path, tmp_path / "missing-directory" / "restore.db")

    no_manifest_path = tmp_path / "snapshot-without-manifest.db"
    no_manifest_path.write_bytes(backup_path.read_bytes())
    with pytest.raises(ValueError, match="manifest is missing"):
        restore_database(no_manifest_path, invalid_target)
    assert not invalid_target.exists()

    bad_manifest_path = tmp_path / "snapshot-with-invalid-manifest.db"
    bad_manifest_path.write_bytes(backup_path.read_bytes())
    (tmp_path / "snapshot-with-invalid-manifest.db.manifest.json").write_text("{invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest is invalid"):
        restore_database(bad_manifest_path, invalid_target)
    assert not invalid_target.exists()

    existing_target = tmp_path / "existing.db"
    existing_target.write_bytes(b"keep this file")
    with pytest.raises(FileExistsError):
        restore_database(backup_path, existing_target)
    assert existing_target.read_bytes() == b"keep this file"

    manifest_path = tmp_path / "valid-snapshot.db.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["revision"] = "wrong-revision"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest does not match"):
        restore_database(backup_path, invalid_target)
    assert not invalid_target.exists()
    assert inspect_database(db_path)["revision"] == MVP_HEAD
