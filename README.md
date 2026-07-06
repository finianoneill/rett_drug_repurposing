# Rett Drug Repurposing

A publicly available agentic system that performs **in-silico drug repurposing for Rett syndrome** by reasoning over public biomedical data and ranking off-patent compounds as repurposing candidates.

> **Status:** Phase 2 — two strategies live: **target-based** (Open Targets + ChEMBL) and **signature reversal** (a Mecp2-null mouse cortex expression signature reversed against LINCS L1000 perturbagens via SigCom LINCS). See `docs/IMPLEMENTATION_BRIEF.md` for the Phase 1 scope and `docs/rett-repurposing-design-doc.md` §8 for the phased roadmap.

## Architecture

Two services, plus an embedded DuckDB file on a bind-mounted volume:

```
Browser ──► frontend (Next.js, :3000) ──► backend (FastAPI, :8000) ──► ./data/rett_repurposing.duckdb
```

The Next.js Route Handler at `/api/repurpose` proxies SSE from the backend (`http://backend:8000`) to the browser. CORS is a non-issue because the browser only ever talks to the frontend container.

## Quickstart

Requires Docker Desktop (or any Docker Engine ≥ 24 with Compose v2).

```bash
git clone <repo>
cd rett_drug_repurposing
cp .env.example .env                   # set ANTHROPIC_API_KEY
make build                             # build both images
make fetch                             # one-time: populate ./data/rett_repurposing.duckdb
make up                                # start backend + frontend
# Open http://localhost:3000
```

## Build and deploy with Docker Compose

Two services live in `docker-compose.yml`:

- `backend` — FastAPI on port `8000`, reads `./data/rett_repurposing.duckdb` (bind-mounted).
- `frontend` — Next.js on port `3000`, proxies `/api/repurpose` to `http://backend:8000` over Docker's internal DNS.

`docker-compose.override.yml` is committed and applied automatically by `docker compose up`. It enables hot-reload (uvicorn `--reload`, Next.js dev server), source-mount overlays, and `LOG_LEVEL=DEBUG`. Keep it for development; for a leaner, production-shaped run see *Production-shaped deploy* below.

### Prerequisites

1. **Docker Desktop running.** Verify with `docker info`.
2. **`.env` populated.** Copy from the template and set the key the backend may use for LLM calls:
   ```bash
   cp .env.example .env
   # edit .env: ANTHROPIC_API_KEY=sk-ant-...
   ```
   Phase 1 doesn't yet call the LLM, but `pydantic-settings` reads the file at startup.
3. **No host process bound to ports `3000` or `8000`.** Stop any local dev servers first.

### 1. Build images

```bash
make build                             # equivalent to: docker compose build
```

The first build takes ~2–4 min (uv resolves the Python lockfile, pnpm installs Node deps). Subsequent builds are cached unless `pyproject.toml`, `uv.lock`, `frontend/package.json`, or `frontend/pnpm-lock.yaml` change.

### 2. Populate the DuckDB store

```bash
make fetch                             # runs the three fetcher scripts inside the backend container
```

This runs, in order: `fetch_opentargets.py` → `fetch_chembl.py` (Phase 1) → `fetch_geo.py` → `build_signature.py` → `fetch_lincs.py` (Phase 2) → `build_local_store.py`, leaving `./data/rett_repurposing.duckdb` on disk. The host owns `./data/`; the container mounts it read-write only during the fetch.

`make fetch` is idempotent — re-run it any time you want fresh data. All APIs (Open Targets, ChEMBL, NCBI GEO, SigCom LINCS) are unauthenticated. Phase 2 adds a GEO counts download (~20 MB) and ~180 ChEMBL name lookups, so end-to-end is ~1–3 min. The mouse→human ortholog table is committed (`make fetch-orthologs` to refresh it).

⚠️ **DuckDB single-writer rule.** Do **not** run `make fetch` while `make up` is running. The fetcher needs a write lock on the file; the backend holds a read lock. Stop the stack with `make down` first, or use the host-mode flow (§ *Host-mode development*).

### 3. Start the stack

```bash
make up                                # foreground: docker compose up
make up-detached                       # background: docker compose up -d
```

Health gates:

```bash
curl http://localhost:8000/health      # → {"status":"ok","duckdb_ready":true}
curl http://localhost:3000/api/health  # same payload, proxied through Next.js
```

The browser only ever talks to the frontend container — there is no CORS preflight. Open <http://localhost:3000> and click **Run analysis**.

### 4. Inspect logs

```bash
make logs                              # tail both services (docker compose logs -f)
docker compose logs -f backend         # backend only
docker compose logs -f frontend        # frontend only
```

### 5. Stop the stack

```bash
make down                              # docker compose down (preserves data/)
make clean                             # docker compose down -v + remove .venv/, node_modules/, .next/
```

`make down` does **not** delete `./data/rett_repurposing.duckdb` — that's a host-bound directory, not a Docker volume. To wipe data, `rm -rf data/` from the host.

### Common operations

| Task | Command |
|---|---|
| Rebuild after `pyproject.toml` change | `docker compose build backend` |
| Rebuild after `package.json` change | `docker compose build frontend` |
| One-shot script in the backend image | `docker compose run --rm backend python scripts/fetch_chembl.py` |
| Open a shell in the backend container | `docker compose exec backend bash` |
| Inspect the DuckDB file from the host | `duckdb data/rett_repurposing.duckdb` (requires the DuckDB CLI, stack stopped) |
| Reset everything | `make clean && rm -rf data/* && make build && make fetch && make up` |

### Troubleshooting

- **`duckdb_ready: false`** — the file doesn't exist yet. Run `make fetch`.
- **`Cannot reach backend at http://backend:8000`** in the frontend log — the backend's healthcheck failed. Check `docker compose logs backend`. Common cause: missing or empty `data/rett_repurposing.duckdb`.
- **`Cannot open database in read-only mode: database does not exist`** — same root cause; run `make fetch`.
- **`port is already allocated`** — another process is on `:3000` or `:8000`. Identify with `lsof -i :3000` (or `:8000`) and stop it, or change the host-side port mapping in `docker-compose.yml`.
- **Hot-reload not picking up changes on macOS** — file events sometimes drop through bind mounts. The override sets `WATCHPACK_POLLING=true` for the frontend; if Python reload misses changes, restart with `docker compose restart backend`.
- **`make fetch` errors with a write-lock conflict** — `make up` is still running. `make down` first.

### Production-shaped deploy

The committed `docker-compose.override.yml` is **dev-mode by design** (hot-reload, source mounts, debug logging). For a leaner deployment that mirrors a future production target:

```bash
docker compose -f docker-compose.yml up --build
```

Passing `-f docker-compose.yml` explicitly skips the override. The backend then runs the baked-in `CMD` (`uvicorn ... --host 0.0.0.0 --port 8000`, no `--reload`) and the frontend runs the dev `pnpm dev` baked into its Dockerfile. A dedicated `Dockerfile` stage that runs `next build && next start` is a Phase 2 deliverable; for now this is "production-shaped," not "production-ready." Don't expose this to the public internet.

## Host-mode development

For fast iteration on Python-only changes (tests, fetchers, lint), bypass Docker:

```bash
make install                           # uv sync + (cd frontend && pnpm install)
make test                              # pytest
make lint                              # ruff + frontend eslint
make typecheck                         # mypy + tsc
make fetch-host                        # populate the DuckDB file from the host
```

Host-mode tests are network-free (HTTP fetchers use `httpx.MockTransport`, store tests use in-memory DuckDB). The `validation` marker is opt-in and requires a populated `data/rett_repurposing.duckdb`:

```bash
uv run pytest -m validation -s         # oracle-coverage check, requires real data
```

## Repository layout

See `docs/IMPLEMENTATION_BRIEF.md` §4 for the full structure. Highlights:

- `src/rett_repurposing/` — Python package (config, models, store, fetchers, strategies, graph, api).
- `scripts/` — fetchers and the local-store builder.
- `frontend/` — Next.js 15 App Router app.
- `docker/` — backend and frontend Dockerfiles.
- `notebooks/journal/` — learning journal (user-authored).

## Data sources

See `DATA_LICENSES.md` for full attribution.

Phase 1 sources:

- **Open Targets Platform** (CC0) — disease–target associations, known drugs.
- **ChEMBL** (CC BY-SA 3.0) — drug enrichment (approval status, SMILES, ATC).

Phase 2 sources:

- **GEO** (NIH public domain) — Mecp2-null mouse cortex RNA-seq (GSE300534) for the disease signature.
- **SigCom LINCS / LINCS L1000** (open) — perturbagen signatures for reversal scoring.
- **MGI** (free, attribution requested) — mouse→human ortholog mapping.

## Scope by phase

- **Phase 1 (done):** target-based strategy end-to-end — OT + ChEMBL → DuckDB → LangGraph → FastAPI SSE → Next.js streaming UI.
- **Phase 2 (this release):** signature-reversal strategy — a Rett expression signature (Mecp2-null vs WT cortex, GEO) reversed against LINCS L1000 perturbagens (SigCom LINCS), resolved to ChEMBL drugs, added as a second LangGraph node. Select strategies in the UI or via `enabled_strategies` on `POST /repurpose`.
- **Out (later phases):** network proximity (Phase 3), real ensemble synthesizer (Phase 4), Bayesian aggregation, BioNeMo, MCP servers, multi-disease, auth.

The synthesizer remains a passthrough — when both strategies run it surfaces one deterministically (real cross-strategy aggregation is Phase 4). Run the strategies individually to compare their candidate lists.

## License

Apache-2.0. See `LICENSE`.
