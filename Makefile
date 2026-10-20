# Thin wrappers around the root package.json scripts (cross-platform users can run `pnpm run <script>` directly).
AGENT := uv run --directory services/agent

.PHONY: install up down migrate seed reset-demo verify-seed kb-sync kb-index dev test lint format types eval demo-run demo-check demo-record demo-verify demo-cleanup

install:
	pnpm install
	uv sync --directory services/agent

up:
	pnpm run db:up

down:
	pnpm run db:down

migrate:
	pnpm run db:migrate

seed:
	pnpm run db:seed

kb-sync:
	pnpm run kb:sync

kb-index:
	pnpm run kb:index

reset-demo:
	pnpm run db:reset-demo

demo-run demo-check demo-record demo-verify demo-cleanup:
	pnpm run $(subst demo-,demo:,$@)

verify-seed:
	pnpm run db:verify

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
