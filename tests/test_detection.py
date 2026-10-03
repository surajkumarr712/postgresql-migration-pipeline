from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "detect_added_migrations.py"
ZERO_SHA = "0" * 40


def git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit_all(repository: Path, message: str) -> str:
    git(repository, "add", ".")
    git(repository, "commit", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def run_detector(repository: Path, base: str, head: str) -> list[str]:
    output = repository / "changed-migrations.txt"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--base",
            base,
            "--head",
            head,
            "--output",
            str(output),
        ],
        cwd=repository,
        check=True,
    )
    return output.read_text(encoding="utf-8").splitlines()


def test_new_branch_detects_all_existing_migrations(tmp_path: Path):
    git(tmp_path, "init", "-b", "staging")
    git(tmp_path, "config", "user.name", "Pipeline Test")
    git(tmp_path, "config", "user.email", "pipeline@example.com")
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "V0001__first.sql").write_text("SELECT 1;\n", encoding="utf-8")
    head = commit_all(tmp_path, "Initial staging commit")

    assert run_detector(tmp_path, ZERO_SHA, head) == ["migrations/V0001__first.sql"]


def test_regular_push_detects_only_new_migrations(tmp_path: Path):
    git(tmp_path, "init", "-b", "staging")
    git(tmp_path, "config", "user.name", "Pipeline Test")
    git(tmp_path, "config", "user.email", "pipeline@example.com")
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "V0001__first.sql").write_text("SELECT 1;\n", encoding="utf-8")
    base = commit_all(tmp_path, "First migration")

    (tmp_path / "README.md").write_text("Documentation update\n", encoding="utf-8")
    (migrations / "V0002__second.sql").write_text("SELECT 2;\n", encoding="utf-8")
    head = commit_all(tmp_path, "Second migration")

    assert run_detector(tmp_path, base, head) == ["migrations/V0002__second.sql"]
