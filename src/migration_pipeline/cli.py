from __future__ import annotations

import argparse
import os
from pathlib import Path

from .runner import MigrationError
from .runner import apply_migrations
from .runner import discover_migrations


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply versioned PostgreSQL migrations as a deployment gate."
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL connection URL; defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=Path("migrations"),
    )
    parser.add_argument(
        "--changed-file-list",
        type=Path,
        help="Newline-delimited migration paths detected in the staging commit.",
    )
    parser.add_argument(
        "--all-pending",
        action="store_true",
        help="Scan every migration and apply all pending versions.",
    )
    parser.add_argument(
        "--commit-sha",
        default=os.environ.get("GITHUB_SHA", "local"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required")
    if args.all_pending == bool(args.changed_file_list):
        raise SystemExit("Choose exactly one of --all-pending or --changed-file-list")

    selected = None
    if args.changed_file_list:
        if not args.changed_file_list.exists():
            raise SystemExit(f"Changed-file list not found: {args.changed_file_list}")
        selected = [
            Path(line.strip())
            for line in args.changed_file_list.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    try:
        migrations = discover_migrations(args.migrations_dir, selected)
        apply_migrations(
            args.database_url,
            migrations,
            args.commit_sha,
            dry_run=args.dry_run,
        )
    except MigrationError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
