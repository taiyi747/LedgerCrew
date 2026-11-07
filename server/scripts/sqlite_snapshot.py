"""Consistent SQLite snapshot and restore to new paths only.

Run from server/ with Python 3.11. The tool never overwrites a database. It
does not run Alembic or decide whether a schema revision is safe to deploy.
"""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ValueError(f"Database file does not exist: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def inspect_database(path: Path) -> dict[str, str]:
    try:
        with closing(_readonly(path)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError(f"SQLite integrity_check failed: {path}")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError(f"SQLite foreign_key_check failed: {path}")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "alembic_version" not in tables:
                raise ValueError(f"Alembic version table is missing: {path}")
            rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
            if len(rows) != 1:
                raise ValueError(f"Expected exactly one Alembic revision: {path}")
            return {"revision": rows[0][0], "integrity_check": "ok", "foreign_key_check": "ok"}
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"SQLite database cannot be validated: {path}") from exc


def _new_target(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        raise ValueError("Source and target must differ")
    if not target.parent.is_dir():
        raise ValueError(f"Target directory does not exist: {target.parent}")
    # Exclusive creation prevents replacing an existing database, including a
    # file created by another process after the initial path check.
    with target.open("xb"):
        pass


def backup_database(source: Path, target: Path) -> dict[str, str]:
    info = inspect_database(source)
    manifest_path = target.with_name(f"{target.name}.manifest.json")
    if manifest_path.exists():
        raise FileExistsError(manifest_path)
    _new_target(source, target)
    with closing(_readonly(source)) as source_db, closing(sqlite3.connect(target)) as target_db:
        source_db.backup(target_db)
    if inspect_database(target)["revision"] != info["revision"]:
        raise ValueError("Backup Alembic revision differs from source")
    manifest = {
        "backup_time_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "revision": info["revision"],
        "sha256": _digest(target),
        "integrity_check": "ok",
        "foreign_key_check": "ok",
    }
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest


def restore_database(backup: Path, target: Path) -> dict[str, str]:
    info = inspect_database(backup)
    manifest_path = backup.with_name(f"{backup.name}.manifest.json")
    if not manifest_path.is_file():
        raise ValueError(f"Backup manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Backup manifest is invalid: {manifest_path}") from exc
    if manifest.get("revision") != info["revision"] or manifest.get("sha256") != _digest(backup):
        raise ValueError("Backup manifest does not match backup file")
    _new_target(backup, target)
    with closing(_readonly(backup)) as source_db, closing(sqlite3.connect(target)) as target_db:
        source_db.backup(target_db)
    restored = inspect_database(target)
    if restored["revision"] != info["revision"]:
        raise ValueError("Restored Alembic revision differs from backup")
    return restored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "backup", "restore"):
        subparser = commands.add_parser(command)
        subparser.add_argument("source", type=Path)
        if command != "inspect":
            subparser.add_argument("target", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "inspect":
        result = inspect_database(arguments.source)
    elif arguments.command == "backup":
        result = backup_database(arguments.source, arguments.target)
    else:
        result = restore_database(arguments.source, arguments.target)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
