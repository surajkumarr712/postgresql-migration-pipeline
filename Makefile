.PHONY: install test migrate docker-up docker-down

install:
	python -m pip install -e '.[dev]'

test:
	pytest

migrate:
	postgres-migrate --database-url "$(DATABASE_URL)" --migrations-dir migrations --all-pending

docker-up:
	docker compose up -d --wait

docker-down:
	docker compose down -v
