from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from migration_pipeline.runner import apply_migrations
from migration_pipeline.runner import discover_migrations


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.integration


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
def test_applies_once_and_tracks_history():
    assert DATABASE_URL is not None
    root = Path(__file__).resolve().parents[1]
    migrations = discover_migrations(root / "migrations")

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS customer_accounts CASCADE")
        connection.execute("DROP TABLE IF EXISTS schema_migrations CASCADE")

    assert apply_migrations(DATABASE_URL, migrations, "integration-test") == 2
    assert apply_migrations(DATABASE_URL, migrations, "integration-test-rerun") == 0

    with psycopg.connect(DATABASE_URL) as connection:
        count = connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        status_column = connection.execute(
            """
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_name = 'customer_accounts' AND column_name = 'status'
            """
        ).fetchone()[0]
    assert count == 2
    assert status_column == 1


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
def test_failed_batch_rolls_back_every_new_migration(tmp_path: Path):
    assert DATABASE_URL is not None
    (tmp_path / "V0001__create_rollback_probe.sql").write_text(
        "CREATE TABLE rollback_probe (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    (tmp_path / "V0002__force_failure.sql").write_text(
        "INSERT INTO rollback_probe (id) VALUES (1);\nSELECT 1 / 0;\n",
        encoding="utf-8",
    )
    migrations = discover_migrations(tmp_path)

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS rollback_probe CASCADE")
        connection.execute("DROP TABLE IF EXISTS schema_migrations CASCADE")

    with pytest.raises(psycopg.errors.DivisionByZero):
        apply_migrations(DATABASE_URL, migrations, "rollback-test")

    with psycopg.connect(DATABASE_URL) as connection:
        probe_table = connection.execute(
            "SELECT to_regclass('public.rollback_probe')"
        ).fetchone()[0]
        history_table = connection.execute(
            "SELECT to_regclass('public.schema_migrations')"
        ).fetchone()[0]

    assert probe_table is None
    assert history_table is None
