from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path


NAME = re.compile(r"^migrations/V\d{4}__[a-z0-9_]+\.sql$")
ZERO_SHA = "0" * 40


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, default=Path("changed-migrations.txt"))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.all:
        files = sorted(str(path) for path in Path("migrations").glob("V*.sql"))
    else:
        if args.base == ZERO_SHA:
            # A newly created staging branch has no "before" commit. Treat all
            # migrations present at its head as additions for the first run.
            output = git(
                "ls-tree",
                "-r",
                "--name-only",
                args.head,
                "--",
                "migrations",
            )
        else:
            output = git(
                "diff",
                "--diff-filter=A",
                "--name-only",
                args.base,
                args.head,
                "--",
                "migrations",
            )
        files = sorted(line for line in output.splitlines() if line)

    invalid = [path for path in files if not NAME.fullmatch(path)]
    if invalid:
        raise SystemExit(
            "Invalid migration filename(s): " + ", ".join(invalid) + ". "
            "Use migrations/V0001__description.sql."
        )

    args.output.write_text("".join(f"{path}\n" for path in files), encoding="utf-8")
    print(f"Detected {len(files)} migration file(s).")
    for path in files:
        print(f"  {path}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as stream:
            stream.write(f"count={len(files)}\n")
            stream.write(f"file_list={args.output}\n")


if __name__ == "__main__":
    main()
