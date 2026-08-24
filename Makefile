SUPABASE_COMPOSE = docker compose -f docker-compose.yml -f docker-compose.supabase.yml

.PHONY: install install-agent install-ingestion install-dev run dev-db migrate migration-current supabase-config supabase-migrate supabase-current supabase-up supabase-stop ingest-local test-db test test-agent test-data lint format typecheck openapi-check migration-check dvc-check check clean

install:
	python -m pip install -e .

install-agent:
	python -m pip install -e ".[agent-yolo]"

install-ingestion:
	python -m pip install -e ".[ingestion]"

install-dev:
	python -m pip install --upgrade pip
	python -m pip install -e ".[agent,ingestion]" --group dev

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

dev-db:
	docker compose up -d --wait postgres

migrate:
	python -m alembic upgrade head

migration-current:
	python -m alembic current --check-heads

supabase-config:
	$(SUPABASE_COMPOSE) config --quiet

supabase-migrate:
	$(SUPABASE_COMPOSE) run --rm --no-deps --build backend python -m alembic upgrade head

supabase-current:
	$(SUPABASE_COMPOSE) run --rm --no-deps backend python -m alembic current --check-heads

supabase-up:
	$(SUPABASE_COMPOSE) up -d --build --wait --wait-timeout 120 backend

supabase-stop:
	$(SUPABASE_COMPOSE) stop backend

ingest-local:
	python scripts/label_guardian_run_ingestion.py --source local --selector kitti

test-db:
	docker compose --profile test up -d --wait postgres-test

test:
	pytest tests/ -v

test-agent:
	pytest tests/test_agents/ -v

test-data:
	pytest tests/test_data/ -v

lint:
	python -m ruff check src/ tests/ migrations/ scripts/check_migrations.py scripts/check_openapi.py scripts/label_guardian_*.py

format:
	ruff format src/ tests/

typecheck:
	python -m mypy src/

openapi-check:
	python scripts/check_openapi.py

migration-check:
	python scripts/check_migrations.py

dvc-check:
	python -m dvc doctor

check: lint typecheck openapi-check migration-check test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
