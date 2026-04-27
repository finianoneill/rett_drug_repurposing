.PHONY: install up up-detached down logs build fetch fetch-host test lint typecheck clean

# ---- Docker Compose lifecycle ----
build:
	docker compose build

up:
	docker compose up

up-detached:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# ---- Host-mode installs (for running tests, linters, fetchers locally) ----
install:
	uv sync
	cd frontend && pnpm install

# ---- Data fetching ----
# Default: run inside the backend container (consistent env, network).
fetch:
	docker compose run --rm backend python scripts/fetch_opentargets.py
	docker compose run --rm backend python scripts/fetch_chembl.py
	docker compose run --rm backend python scripts/build_local_store.py

# Host-mode fetch for fast iteration; requires `make install` first.
fetch-host:
	uv run python scripts/fetch_opentargets.py
	uv run python scripts/fetch_chembl.py
	uv run python scripts/build_local_store.py

# ---- Quality gates (run on host for speed; CI can run in container) ----
test:
	uv run pytest -v

lint:
	uv run ruff check src/ tests/ scripts/
	uv run ruff format --check src/ tests/ scripts/
	cd frontend && pnpm lint

typecheck:
	uv run mypy src/
	cd frontend && pnpm typecheck

clean:
	docker compose down -v
	rm -rf .venv frontend/node_modules frontend/.next
