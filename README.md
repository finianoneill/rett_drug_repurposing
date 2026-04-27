# Rett Drug Repurposing

A publicly available agentic system that performs **in-silico drug repurposing for Rett syndrome** by reasoning over public biomedical data and ranking off-patent compounds as repurposing candidates.

> **Status:** Phase 1 — target-based repurposing strategy via Open Targets + ChEMBL. See `docs/IMPLEMENTATION_BRIEF.md` for scope and `docs/rett-repurposing-design-doc.md` for the broader vision.

## Architecture

Two services, plus an embedded DuckDB file on a bind-mounted volume:

```
Browser ──► frontend (Next.js, :3000) ──► backend (FastAPI, :8000) ──► ./data/rett_repurposing.duckdb
```

The Next.js Route Handler at `/api/repurpose` proxies SSE from the backend (`http://backend:8000`) to the browser. CORS is a non-issue because the browser only ever talks to the frontend container.

## Quickstart

Requires Docker Desktop.

```bash
git clone <repo>
cd rett_drug_repurposing
cp .env.example .env                   # fill in ANTHROPIC_API_KEY
make build                             # build images
make fetch                             # populate ./data/rett_repurposing.duckdb
make up                                # start backend + frontend
# Open http://localhost:3000
```

## Host-mode development

For fast iteration on Python-only changes (tests, fetchers, lint):

```bash
make install                           # uv sync + pnpm install
make test                              # pytest
make lint                              # ruff + frontend eslint
make typecheck                         # mypy + tsc
make fetch-host                        # populate the DuckDB file from the host
```

⚠️ **DuckDB single-writer rule.** Don't run `make fetch` while `make up` is running — the fetcher acquires a write lock on the DuckDB file and conflicts with the backend.

## Repository layout

See `docs/IMPLEMENTATION_BRIEF.md` §4 for the full structure. Highlights:

- `src/rett_repurposing/` — Python package (config, models, store, fetchers, strategies, graph, api).
- `scripts/` — fetchers and the local-store builder.
- `frontend/` — Next.js 15 App Router app.
- `docker/` — backend and frontend Dockerfiles.
- `notebooks/journal/` — learning journal (user-authored).

## Data sources

See `DATA_LICENSES.md` for full attribution. Phase 1 sources:

- **Open Targets Platform** (CC0) — disease–target associations, known drugs.
- **ChEMBL** (CC BY-SA 3.0) — drug enrichment (approval status, SMILES, ATC).

## Phase 1 scope

In: target-based strategy end-to-end, single LangGraph node, FastAPI SSE, Next.js streaming UI.
Out: signature reversal, network proximity, Bayesian aggregation, BioNeMo, MCP servers, multi-disease, auth.

## License

Apache-2.0. See `LICENSE`.
