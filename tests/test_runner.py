from pathlib import Path

import pytest

from migration_pipeline.runner import MigrationError
from migration_pipeline.runner import discover_migrations


def write(path: Path, text: str = "SELECT 1;") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_discovers_migrations_in_version_order(tmp_path: Path):
    write(tmp_path / "V0002__second.sql")
    write(tmp_path / "V0001__first.sql")

    migrations = discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == [1, 2]
    assert all(len(migration.checksum) == 64 for migration in migrations)


def test_rejects_duplicate_versions(tmp_path: Path):
    write(tmp_path / "V0001__first.sql")
    write(tmp_path / "V0001__duplicate.sql")

    with pytest.raises(MigrationError, match="Duplicate migration version"):
        discover_migrations(tmp_path)


def test_rejects_invalid_names_when_selected(tmp_path: Path, monkeypatch):
    migration = write(tmp_path / "1_bad_name.sql")
    monkeypatch.chdir(tmp_path.parent)

    with pytest.raises(MigrationError, match="Invalid migration name"):
        discover_migrations(tmp_path, [migration])


def test_rejects_selected_file_outside_directory(tmp_path: Path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    outside = write(tmp_path / "V0001__outside.sql")

    with pytest.raises(MigrationError, match="outside"):
        discover_migrations(migrations, [outside])
