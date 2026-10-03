# PostgreSQL Migration Pipeline

A production-oriented migration gate that detects SQL migrations introduced by a staging update, verifies whether each migration already ran, applies new migrations in a single PostgreSQL transaction, and blocks deployment if anything fails.

## Deployment flow

```text
Commit is pushed or merged into staging
        |
Pipeline detects migration files added by that commit
        |
Checks schema_migrations for prior execution and checksum changes
        |
Executes new migrations inside one PostgreSQL transaction
        |
Success -> records migrations and opens the deployment gate
Failure -> rolls back the batch, fails the workflow, stops deployment
```

## Why this design is safe

- **Transactional batch:** PostgreSQL DDL and tracking records commit together. A failure rolls back every migration applied by that run.
- **Execution history:** `schema_migrations` records the version, filename, SHA-256 checksum, commit SHA, duration, and timestamp.
- **Immutable history:** editing a previously applied migration causes a checksum failure. Changes must be introduced through a new version.
- **Concurrency control:** a PostgreSQL advisory transaction lock prevents two deployments from applying migrations simultaneously.
- **Least credential exposure:** the staging connection string is read from a protected GitHub environment secret and never written to the repository or logs.
- **Deployment gate:** the deployment job depends on migration success, so any database failure stops the release.

## Migration convention

Migration files live in `migrations/` and use an ordered version:

```text
V0001__create_customer_accounts.sql
V0002__add_account_status.sql
```

Never edit a migration after it has run. Add a new migration instead.

## Local setup

Requirements: Python 3.11+ and Docker.

```bash
docker compose up -d --wait
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
export DATABASE_URL='postgresql://postgres:postgres@localhost:5432/app'
export TEST_DATABASE_URL="$DATABASE_URL"
postgres-migrate --migrations-dir migrations --all-pending
pytest
```

Run the command again to confirm that applied migrations are skipped.

## Configure GitHub staging

1. Create a GitHub environment named `staging`.
2. Add an environment secret named `STAGING_DATABASE_URL`.
3. Restrict the environment with required reviewers if appropriate.
4. Protect the `staging` branch and require the migration workflow.
5. Replace the placeholder command in the `deployment-gate` job with the real deployment step.

The workflow runs automatically when a commit reaches `staging`. Manual runs scan all migration files and safely apply only versions not already recorded.

## Rollback demonstration

`examples/V9999__failing_example.sql.disabled` contains a deliberate error. Copy it into `migrations/` with the `.sql` suffix in a disposable database to observe the transaction rollback and failed deployment gate.
