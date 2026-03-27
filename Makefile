.PHONY: dev test lint typecheck format docker-build docker-up docker-down

dev:
	uv run uvicorn cherry_bomb.main:create_app --factory --reload --port 8000

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check src/ tests/

typecheck:
	uv run mypy src/

format:
	uv run ruff format src/ tests/

docker-build:
	docker compose -f infra/docker/docker-compose.yml build

docker-up:
	docker compose -f infra/docker/docker-compose.yml up

docker-down:
	docker compose -f infra/docker/docker-compose.yml down
