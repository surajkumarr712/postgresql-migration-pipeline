from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg
from psycopg import Connection


MIGRATION_NAME = re.compile(r"^V(?P<version>\d{4})__(?P<name>[a-z0-9_]+)\.sql$")
LOCK_NAME = "postgres-staging-migration-pipeline"


class MigrationError(RuntimeError):
    """Raised when migration discovery or execution is unsafe."""


@dataclass(frozen=True, order=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str

    @property
    def filename(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class AppliedMigration:
    version: int
    filename: str
    checksum: str


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_migrations(
    migrations_dir: Path,
    selected_files: Iterable[Path] | None = None,
) -> list[Migration]:
    migrations_dir = migrations_dir.resolve()
    if not migrations_dir.is_dir():
        raise MigrationError(f"Migrations directory does not exist: {migrations_dir}")

    if selected_files is None:
        candidates = sorted(migrations_dir.glob("V*.sql"))
    else:
        candidates = []
        for selected in selected_files:
            candidate = selected if selected.is_absolute() else Path.cwd() / selected
            candidate = candidate.resolve()
            try:
                candidate.relative_to(migrations_dir)
            except ValueError as exc:
                raise MigrationError(f"Migration is outside {migrations_dir}: {selected}") from exc
            if not candidate.is_file():
                raise MigrationError(f"Migration file does not exist: {selected}")
            candidates.append(candidate)

    migrations: list[Migration] = []
    versions: dict[int, str] = {}
    for path in candidates:
        match = MIGRATION_NAME.fullmatch(path.name)
        if not match:
            raise MigrationError(
                f"Invalid migration name {path.name!r}; expected V0001__description.sql"
            )
        version = int(match.group("version"))
        if version in versions:
            raise MigrationError(
                f"Duplicate migration version V{version:04d}: {versions[version]} and {path.name}"
            )
        versions[version] = path.name
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                path=path,
                checksum=_checksum(path),
            )
        )
    return sorted(migrations)


def _ensure_history_table(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            filename TEXT NOT NULL UNIQUE,
            checksum CHAR(64) NOT NULL,
            commit_sha TEXT NOT NULL,
            execution_ms INTEGER NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _history(connection: Connection) -> dict[int, AppliedMigration]:
    rows = connection.execute(
        "SELECT version, filename, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {
        row[0]: AppliedMigration(version=row[0], filename=row[1], checksum=row[2])
        for row in rows
    }


def _pending(
    migrations: Iterable[Migration],
    history: dict[int, AppliedMigration],
) -> list[Migration]:
    pending: list[Migration] = []
    for migration in migrations:
        applied = history.get(migration.version)
        if applied is None:
            pending.append(migration)
            continue
        if applied.filename != migration.filename:
            raise MigrationError(
                f"V{migration.version:04d} was recorded as {applied.filename}, "
                f"not {migration.filename}"
            )
        if applied.checksum != migration.checksum:
            raise MigrationError(
                f"Checksum mismatch for applied migration {migration.filename}; "
                "create a new migration instead of editing history"
            )
        print(f"SKIP  {migration.filename} (already applied)")
    return pending


def apply_migrations(
    database_url: str,
    migrations: Iterable[Migration],
    commit_sha: str,
    *,
    dry_run: bool = False,
) -> int:
    selected = list(migrations)
    if not selected:
        print("No migration files were selected; deployment gate is clear.")
        return 0

    with psycopg.connect(database_url, autocommit=False) as connection:
        try:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_NAME,))
            _ensure_history_table(connection)
            pending = _pending(selected, _history(connection))

            if dry_run:
                for migration in pending:
                    print(f"PLAN  {migration.filename}")
                connection.rollback()
                return len(pending)

            for migration in pending:
                started = time.monotonic()
                print(f"APPLY {migration.filename}")
                connection.execute(migration.path.read_text(encoding="utf-8"))
                execution_ms = round((time.monotonic() - started) * 1000)
                connection.execute(
                    """
                    INSERT INTO schema_migrations
                        (version, filename, checksum, commit_sha, execution_ms)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        migration.version,
                        migration.filename,
                        migration.checksum,
                        commit_sha,
                        execution_ms,
                    ),
                )
                print(f"DONE  {migration.filename} ({execution_ms} ms)")

            connection.commit()
            print(f"Migration gate passed: {len(pending)} migration(s) applied.")
            return len(pending)
        except Exception:
            connection.rollback()
            print("Migration failed; the transaction was rolled back. Deployment must stop.")
            raise
