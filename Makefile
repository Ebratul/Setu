# Thin wrappers around the root package.json scripts (cross-platform users can run `pnpm run <script>` directly).
AGENT := uv run --directory services/agent

.PHONY: install up down migrate seed dev test lint format types eval

install:
	pnpm install
	uv sync --directory services/agent

up:
	pnpm run db:up

down:
	pnpm run db:down

migrate:
	@if [ -f services/agent/alembic.ini ]; then $(AGENT) alembic upgrade head; \
	else echo "migrate: Alembic is configured in Phase 1.1"; fi

seed:
	@if [ -f services/agent/seed/load.py ]; then $(AGENT) python -m seed.load; \
	else echo "seed: seed loaders are added in Phase 1.2"; fi

dev:
	pnpm run dev

test:
	pnpm run test

lint:
	pnpm run lint

format:
	pnpm run format

types:
	./scripts/gen-types.sh

eval:
	@if [ -f services/agent/eval/run.py ]; then $(AGENT) python -m eval.run; \
	else echo "eval: evaluation harness is added in Phase 7.2"; fi
