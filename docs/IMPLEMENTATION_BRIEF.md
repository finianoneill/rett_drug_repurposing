# Rett Syndrome Drug Repurposing — Phase 1 Implementation Brief

*A technical brief for Claude Code. Scope is Phase 1 only: target-based repurposing strategy, end-to-end, for Rett syndrome.*

---

## 0. How to Use This Brief

You are building **Phase 1** of an in-silico drug repurposing system for Rett syndrome. The full multi-phase design lives in `DESIGN.md` (companion document) — read it for context, but build only what this brief specifies.

**Operating principles:**

1. **Ship one strategy end-to-end before adding others.** No work on signature reversal, network proximity, or Bayesian aggregation until Phase 1 is shipped and validated.
2. **Match the contracts in this brief exactly.** Pydantic model field names, the `Strategy` ABC, and DuckDB schemas are interfaces other phases depend on.
3. **When the brief is silent, decide and proceed.** Don't ask for permission on choices like which logging library, which lint config, etc. When in doubt, follow the conventions in §16.
4. **When the brief specifies "verify" on a fact (an external ID, an API field name), actually verify it via API call before hardcoding.** External ontologies and APIs drift; do not trust this document over a live API response.

---

## 1. Project Context

**Goal:** Given Rett syndrome as input, produce a ranked list of off-patent / approved compounds as repurposing candidates, each accompanied by a human-readable evidence trail explaining why the system surfaced it.

**Why Rett:** Single causal gene (MECP2) but undruggable target, forcing all viable strategies to operate on downstream pathways. Trofinetide (Daybue, IGF-1 analog, FDA-approved 2023) acts as a built-in oracle — if Phase 1 surfaces IGF-1 axis modulators in the top results, the methodology works.

**Phase 1 strategy: target-based.** Use Open Targets to identify high-confidence targets associated with Rett, then find approved drugs hitting those targets via ChEMBL. Rank candidates by combining target-disease association strength and drug-target evidence quality.

---

## 2. Phase 1 Scope (What You're Building)

You are shipping a working slice that does the following:

1. **Fetches** Rett-associated targets and known drugs from Open Targets and ChEMBL.
2. **Stores** the result in a local DuckDB file with a stable schema.
3. **Implements one repurposing strategy** (`target_based`) behind a `Strategy` ABC.
4. **Orchestrates** a single LangGraph node executing that strategy with a supervisor + synthesizer harness (the synthesizer is a passthrough at v0 but the wiring exists).
5. **Exposes** a FastAPI endpoint that streams candidates over SSE.
6. **Renders** a Next.js page showing a ranked candidate list with collapsible evidence trails per candidate.

What's **not** in Phase 1: signature reversal, network proximity, Bayesian aggregation, BioNeMo, MCP server wrappers, Temporal, multi-disease support, authentication, user state.

---

## 3. Technical Stack

| Layer | Choice | Version |
|---|---|---|
| Python | uv-managed | 3.12 |
| Backend framework | FastAPI | latest |
| Streaming | SSE via `sse-starlette` | latest |
| Orchestration | LangGraph | latest |
| Local store | DuckDB | latest (Python bindings) |
| Models | Pydantic | v2 |
| HTTP client | httpx (async) | latest |
| LLM | Anthropic Claude (via SDK) | claude-opus-4-7 (env-configurable) |
| Logging | structlog | latest |
| Testing | pytest + pytest-asyncio | latest |
| Linting | ruff | latest |
| Type-checking | mypy (strict on `src/`) | latest |
| Frontend | Next.js (App Router) | 15+ |
| Frontend lang | TypeScript | strict mode |
| Frontend pkg manager | pnpm | latest |
| UI components | shadcn/ui + Tailwind | latest |
| Streaming UI | Vercel AI SDK | latest |
| Containerization | Docker Compose v2 | Docker Desktop |

Use `uv` for Python dependency management. Use `pnpm` for the frontend. **All services run via Docker Compose** for local development — see §5b for the architecture.

---

## 4. Repository Structure

Build to this layout. Do not deviate without flagging.

```
rett-repurposing/
├── README.md
├── DESIGN.md                          # already exists, do not edit
├── IMPLEMENTATION_BRIEF.md            # this file, do not edit
├── DATA_LICENSES.md                   # create per §6.5
├── LICENSE                            # Apache-2.0
├── .gitignore                         # already exists
├── .python-version                    # "3.12"
├── pyproject.toml
├── uv.lock                            # commit this
├── .env.example                       # template; .env is gitignored
├── Makefile                           # common dev tasks (see §5)
│
├── data/                              # gitignored
│   └── .gitkeep
│
├── docker/
│   ├── backend.Dockerfile
│   └── frontend.Dockerfile
├── docker-compose.yml                 # base: production-shaped service definitions
├── docker-compose.override.yml        # dev overrides: hot-reload, source mounts
├── .dockerignore
│
├── notebooks/
│   └── journal/                       # learning journal (user-authored)
│
├── scripts/
│   ├── fetch_opentargets.py
│   ├── fetch_chembl.py
│   └── build_local_store.py
│
├── src/rett_repurposing/
│   ├── __init__.py
│   ├── config.py                      # pydantic-settings, reads .env
│   ├── logging.py                     # structlog setup
│   ├── models.py                      # core Pydantic models (§7)
│   │
│   ├── store/
│   │   ├── __init__.py
│   │   ├── schema.sql                 # DuckDB DDL
│   │   ├── connection.py              # context-managed DuckDB connection
│   │   └── queries.py                 # typed query functions
│   │
│   ├── fetchers/
│   │   ├── __init__.py
│   │   ├── opentargets.py             # OT GraphQL client
│   │   └── chembl.py                  # ChEMBL REST client
│   │
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py                    # Strategy ABC (§8)
│   │   └── target_based.py            # Phase 1 strategy (§9)
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py                   # LangGraph state TypedDict
│   │   ├── supervisor.py              # supervisor node
│   │   ├── nodes.py                   # strategy nodes
│   │   └── synthesizer.py             # passthrough at v0
│   │
│   └── api/
│       ├── __init__.py
│       ├── main.py                    # FastAPI app
│       ├── routes.py                  # /repurpose endpoint
│       └── streaming.py               # SSE helpers
│
├── frontend/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── tsconfig.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── components.json                # shadcn config
│   ├── .env.local.example
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx               # main UI
│       │   └── api/
│       │       └── repurpose/route.ts # proxies to FastAPI SSE
│       ├── components/
│       │   ├── candidate-card.tsx
│       │   ├── evidence-trail.tsx
│       │   └── ui/                    # shadcn primitives
│       └── lib/
│           ├── types.ts               # mirrors Pydantic models
│           └── api-client.ts
│
└── tests/
    ├── conftest.py
    ├── test_models.py
    ├── test_fetchers.py               # use vcrpy or recorded fixtures
    ├── test_strategies.py
    ├── test_store.py
    └── test_api.py
```

---

## 5. Setup & Tooling

Create a `Makefile` with these targets. The default dev workflow is **Docker Compose**; host-mode targets exist for fast iteration on Python-only changes (e.g., test runs).

```makefile
.PHONY: install up down logs build fetch fetch-host test lint typecheck clean

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
```

Add a `pyproject.toml` with ruff configured for line-length 100, target Python 3.12, and mypy in strict mode for `src/rett_repurposing/`. Use `pytest-asyncio` mode `auto`.

---

## 5b. Local Infrastructure (Docker Compose)

Two services, plus the ambient DuckDB file living on a bind-mounted volume. No database container — DuckDB is embedded.

```
                       ┌──────────────────────────────┐
  Host browser ──────► │  frontend  (Next.js, :3000)  │
  http://localhost:3000│                              │
                       └──────────┬───────────────────┘
                                  │  internal network
                                  │  http://backend:8000
                                  ▼
                       ┌──────────────────────────────┐
                       │  backend  (FastAPI, :8000)   │
                       │                              │
                       │  reads/writes DuckDB         │
                       └──────────┬───────────────────┘
                                  │  bind mount
                                  ▼
                       ./data/rett_repurposing.duckdb
                       (host-visible, persists across restarts)
```

**Key architectural decisions:**

1. **The Next.js Route Handler (`/api/repurpose`) calls the backend at `http://backend:8000`** (Docker internal DNS), not `localhost`. This is set via `BACKEND_URL` env var. The browser never talks to the backend directly — all SSE flows backend → frontend container → browser. CORS becomes a non-issue.

2. **DuckDB is a bind-mounted file, not a service.** The host owns `./data/`; the backend container mounts it read-write. This means host-mode tools (e.g., `duckdb` CLI for ad-hoc inspection) work against the same file when the backend is stopped.

3. **DuckDB single-writer rule.** Only one process writes to the DuckDB file at a time. Therefore: do not run `make fetch` while `make up` is running. The fetcher acquires the file; the backend would conflict. If this becomes painful, the answer in v1 is moving to Postgres — not contortions around DuckDB.

4. **`docker-compose.override.yml` is committed**, not gitignored. It's the dev-mode default (hot-reload, source mounts). Production-shaped builds will live in a separate `docker-compose.prod.yml` later. Compose loads `override` automatically — `docker compose up` gives you dev mode for free.

5. **Anonymous volume on `node_modules`** in the frontend service prevents the host bind mount from clobbering the container-built `node_modules` (different binaries between macOS host and Linux container).

### `docker/backend.Dockerfile`

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install uv (the version pin protects reproducibility)
RUN pip install --no-cache-dir uv==0.5.*

# Dependency layer — cached unless lockfile changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Source — invalidates only when code changes
COPY src/ ./src/
COPY scripts/ ./scripts/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uvicorn", "rett_repurposing.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `docker/frontend.Dockerfile`

```dockerfile
FROM node:20-alpine AS base

WORKDIR /app

RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

EXPOSE 3000

CMD ["pnpm", "dev"]
```

### `docker-compose.yml`

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: docker/backend.Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    env_file:
      - .env
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 5s

  frontend:
    build:
      context: .
      dockerfile: docker/frontend.Dockerfile
    ports:
      - "3000:3000"
    environment:
      - BACKEND_URL=http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
```

### `docker-compose.override.yml`

```yaml
services:
  backend:
    command: uvicorn rett_repurposing.api.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./data:/app/data
      - ./src:/app/src
      - ./scripts:/app/scripts
      - ./pyproject.toml:/app/pyproject.toml
    environment:
      - ENV=dev
      - LOG_LEVEL=DEBUG

  frontend:
    volumes:
      - ./frontend/src:/app/src
      - ./frontend/public:/app/public
      - ./frontend/next.config.ts:/app/next.config.ts
      - ./frontend/tsconfig.json:/app/tsconfig.json
      - /app/node_modules    # anonymous volume — prevents host overlay
      - /app/.next           # anonymous volume — keep build artifacts in container
    environment:
      - NODE_ENV=development
      - WATCHPACK_POLLING=true   # Docker Desktop file-watcher reliability on macOS
```

### `.dockerignore`

Mirror `.gitignore` and add Docker-specific exclusions:

```
**/.git
**/.venv
**/__pycache__
**/.pytest_cache
**/.mypy_cache
**/.ruff_cache
**/node_modules
**/.next
**/.DS_Store
data/*
!data/.gitkeep
docker-compose.override.yml   # not needed in production builds
.env
.env.*
!.env.example
```

### Configuration

The backend reads config from `.env` (mounted via `env_file`). Provide `.env.example`:

```
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-opus-4-7
ENV=dev
LOG_LEVEL=INFO
DUCKDB_PATH=/app/data/rett_repurposing.duckdb
```

The frontend reads `BACKEND_URL` from compose-injected env. The Next.js Route Handler at `app/api/repurpose/route.ts` reads `process.env.BACKEND_URL` server-side.

### Quickstart

```bash
git clone <repo>
cd rett-repurposing
cp .env.example .env                  # add ANTHROPIC_API_KEY
make build                            # build images
make fetch                            # populate ./data/rett_repurposing.duckdb
make up                               # start backend + frontend
# Open http://localhost:3000
```

---

## 6. Data Layer

### 6.1 Open Targets Platform (Primary Source)

**API endpoint:** `https://api.platform.opentargets.org/api/v4/graphql`
**Auth:** none required.
**License:** CC0 (data); attribution requested.

**Verify before fetching:** the EFO/MONDO identifier for Rett syndrome. As of the last design check it should be queryable via the `disease(efoId: ...)` resolver. **Run a `search` query first** to confirm the canonical ID rather than hardcoding it from this brief:

```graphql
query SearchRett {
  search(queryString: "Rett syndrome", entityNames: ["disease"]) {
    hits {
      id
      name
      entity
    }
  }
}
```

Take the top disease hit, log the resolved ID, and use it for downstream queries.

**Two queries to implement** in `src/rett_repurposing/fetchers/opentargets.py`:

**Query A — Disease-associated targets** (returns the target ranking the strategy will use):

```graphql
query DiseaseTargets($efoId: String!, $size: Int!) {
  disease(efoId: $efoId) {
    id
    name
    associatedTargets(page: { index: 0, size: $size }) {
      count
      rows {
        target {
          id
          approvedSymbol
          approvedName
          biotype
        }
        score
        datatypeScores {
          id
          score
        }
      }
    }
  }
}
```

Default `size` to 100. The `score` (0–1) is the overall association score; `datatypeScores` breaks it down by evidence type (genetic association, somatic mutations, drugs, expression, pathways, etc.).

**Query B — Known drug-target-disease evidence** (provides the drug evidence chain):

```graphql
query KnownDrugs($efoId: String!, $size: Int!) {
  disease(efoId: $efoId) {
    knownDrugs(size: $size) {
      count
      rows {
        drug {
          id
          name
          drugType
          maximumClinicalTrialPhase
          isApproved
          tradeNames
          synonyms
          mechanismsOfAction {
            rows {
              mechanismOfAction
              targetName
            }
          }
        }
        target {
          id
          approvedSymbol
        }
        phase
        status
        mechanismOfAction
        ctIds
      }
    }
  }
}
```

Default `size` to 500. **Verify field names against the live schema** — Open Targets has versioned schema changes and some fields above may have moved. Use the GraphQL introspection / Voyager tooling at https://api.platform.opentargets.org/api/v4/graphql/browser if a query fails.

**Implementation notes:**

- Use `httpx.AsyncClient` with retry logic (`tenacity` or hand-rolled) — the API occasionally rate-limits.
- Persist raw JSON responses to `data/raw/opentargets/` (gitignored) for reproducibility and offline iteration.
- Do not parse into Pydantic models in the fetcher. Fetchers return raw JSON; parsing happens in `build_local_store.py`.

### 6.2 ChEMBL (Drug Detail Enrichment)

**API endpoint:** `https://www.ebi.ac.uk/chembl/api/data/`
**Auth:** none required.
**License:** CC BY-SA 3.0; attribution required.

For Phase 1, ChEMBL's role is **enrichment only** — Open Targets `knownDrugs` already gives drug-target-disease triplets. ChEMBL adds:

- `max_phase` confirmation (filter to `>= 4`)
- `first_approval` year (proxy for off-patent likelihood)
- `withdrawn_flag` (exclude withdrawn drugs)
- canonical SMILES (for v1 structure work)
- ATC classification (for sanity-checking indication classes)

Implement in `src/rett_repurposing/fetchers/chembl.py`:

```python
async def fetch_molecule(chembl_id: str) -> dict[str, Any]:
    """Fetch /molecule/{chembl_id}.json — return raw JSON."""
    ...

async def fetch_molecules_batch(chembl_ids: list[str]) -> list[dict[str, Any]]:
    """Batch via /molecule.json?molecule_chembl_id__in=ID1,ID2,... (URL length-aware)."""
    ...
```

The Open Targets `drug.id` field returns ChEMBL IDs (format `CHEMBL123`), so the join is direct. Persist raw JSON to `data/raw/chembl/`.

### 6.3 DuckDB Schema

`src/rett_repurposing/store/schema.sql`:

```sql
-- Disease registry (Phase 1: just Rett, but schema supports multi-disease)
CREATE TABLE IF NOT EXISTS diseases (
    efo_id           VARCHAR PRIMARY KEY,
    name             VARCHAR NOT NULL,
    fetched_at       TIMESTAMP NOT NULL
);

-- Targets associated with diseases (from Open Targets)
CREATE TABLE IF NOT EXISTS disease_targets (
    efo_id                   VARCHAR NOT NULL,
    target_ensembl_id        VARCHAR NOT NULL,
    target_symbol            VARCHAR,
    target_name              VARCHAR,
    biotype                  VARCHAR,
    overall_association_score DOUBLE NOT NULL,
    datatype_scores          JSON,                  -- map of datatype -> score
    PRIMARY KEY (efo_id, target_ensembl_id),
    FOREIGN KEY (efo_id) REFERENCES diseases(efo_id)
);

-- Drugs (enriched with ChEMBL data)
CREATE TABLE IF NOT EXISTS drugs (
    chembl_id            VARCHAR PRIMARY KEY,
    name                 VARCHAR NOT NULL,
    drug_type            VARCHAR,
    max_phase            DOUBLE,                    -- ChEMBL canonical
    is_approved          BOOLEAN,
    first_approval_year  INTEGER,
    withdrawn_flag       BOOLEAN,
    trade_names          JSON,                      -- string array
    synonyms             JSON,                      -- string array
    canonical_smiles     VARCHAR,
    atc_classifications  JSON                       -- string array
);

-- Drug-target-disease evidence (from Open Targets knownDrugs)
CREATE TABLE IF NOT EXISTS drug_target_disease (
    chembl_id            VARCHAR NOT NULL,
    target_ensembl_id    VARCHAR NOT NULL,
    efo_id               VARCHAR NOT NULL,
    phase                DOUBLE,
    status               VARCHAR,
    mechanism_of_action  VARCHAR,
    ct_ids               JSON,                      -- ClinicalTrials.gov IDs
    PRIMARY KEY (chembl_id, target_ensembl_id, efo_id),
    FOREIGN KEY (chembl_id) REFERENCES drugs(chembl_id),
    FOREIGN KEY (efo_id) REFERENCES diseases(efo_id)
);

-- Useful views
CREATE VIEW IF NOT EXISTS approved_drugs_for_disease AS
SELECT
    d.chembl_id,
    d.name,
    d.first_approval_year,
    dtd.target_ensembl_id,
    dtd.efo_id,
    dtd.mechanism_of_action,
    dt.overall_association_score,
    dt.target_symbol
FROM drugs d
JOIN drug_target_disease dtd ON d.chembl_id = dtd.chembl_id
JOIN disease_targets dt
    ON dtd.target_ensembl_id = dt.target_ensembl_id
   AND dtd.efo_id = dt.efo_id
WHERE d.is_approved = TRUE
  AND COALESCE(d.withdrawn_flag, FALSE) = FALSE;
```

**Store path:** `data/rett_repurposing.duckdb` (gitignored).

### 6.4 Fetcher Contract

Each fetcher script is independently runnable and idempotent:

```bash
uv run python scripts/fetch_opentargets.py --disease "Rett syndrome" --output data/raw/opentargets/
uv run python scripts/fetch_chembl.py --input data/raw/opentargets/known_drugs.json --output data/raw/chembl/
uv run python scripts/build_local_store.py --output data/rett_repurposing.duckdb
```

`build_local_store.py` is the only script that writes to the DuckDB file. It reads the raw JSON and populates tables transactionally. Re-running it should produce the same DuckDB state (use `INSERT OR REPLACE`).

### 6.5 `DATA_LICENSES.md`

Create this file enumerating sources, licenses, and required attributions. Include Open Targets (CC0), ChEMBL (CC BY-SA 3.0), and a placeholder for sources added in later phases.

---

## 7. Domain Models

`src/rett_repurposing/models.py` — these are the canonical types. Other phases depend on these field names.

```python
from datetime import datetime
from pydantic import BaseModel, Field

class Disease(BaseModel):
    efo_id: str
    name: str

class Target(BaseModel):
    ensembl_id: str
    symbol: str | None = None
    name: str | None = None
    biotype: str | None = None
    overall_association_score: float | None = Field(None, ge=0.0, le=1.0)
    datatype_scores: dict[str, float] = Field(default_factory=dict)

class Drug(BaseModel):
    chembl_id: str
    name: str
    drug_type: str | None = None
    max_phase: float | None = None
    is_approved: bool = False
    first_approval_year: int | None = None
    withdrawn: bool = False
    trade_names: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    canonical_smiles: str | None = None
    atc_classifications: list[str] = Field(default_factory=list)

class EvidenceLink(BaseModel):
    """One link in a candidate's evidence chain."""
    kind: str                         # "drug_targets", "target_associated_with_disease"
    description: str                  # human-readable narrative line
    metadata: dict[str, str | float | int] = Field(default_factory=dict)

class Candidate(BaseModel):
    """A single repurposing candidate output by a strategy."""
    drug: Drug
    target: Target
    score: float = Field(..., ge=0.0)
    score_components: dict[str, float] = Field(default_factory=dict)
    evidence: list[EvidenceLink]
    strategy: str                     # "target_based", etc.

class CandidateList(BaseModel):
    disease: Disease
    candidates: list[Candidate]
    strategy: str
    generated_at: datetime
```

---

## 8. Strategy Interface

`src/rett_repurposing/strategies/base.py`:

```python
from abc import ABC, abstractmethod
from rett_repurposing.models import CandidateList, Disease

class Strategy(ABC):
    """
    Base class for repurposing strategies.

    Each implementation is shaped like an MCP tool: input is a Disease,
    output is a CandidateList. This interface is deliberately stable —
    Phase 5+ will wrap each Strategy as an MCP server with this exact shape.
    """

    name: str       # set by subclass; used in logs and CandidateList.strategy

    @abstractmethod
    async def run(self, disease: Disease) -> CandidateList:
        """Generate ranked candidates for the given disease."""
        ...
```

---

## 9. `target_based` Strategy (Phase 1)

`src/rett_repurposing/strategies/target_based.py`.

**Algorithm:**

1. Query DuckDB `approved_drugs_for_disease` view for the disease.
2. For each `(drug, target)` pair returned, compute a candidate score.
3. Aggregate: if a drug appears via multiple targets, keep the highest-scoring `(drug, target)` pair as the canonical row but record alternative targets in evidence.
4. Sort by score descending, return top N (default 50).

**Score formula (v0 — keep simple, document clearly):**

```
score = (
    0.6 * target.overall_association_score
  + 0.4 * normalized_drug_evidence
)
```

Where `normalized_drug_evidence` is computed per drug as:

```
normalized_drug_evidence = min(1.0, log1p(num_evidence_rows) / log1p(MAX_EVIDENCE))
```

with `MAX_EVIDENCE = 10` as a saturation point. Store both components in `Candidate.score_components` for transparency.

**Evidence chain construction:** for each candidate, build a list like:

```
[
  EvidenceLink(
    kind="target_associated_with_disease",
    description=f"{target.symbol} is associated with Rett syndrome (Open Targets score: {score:.2f})",
    metadata={"source": "Open Targets", "score": score, ...}
  ),
  EvidenceLink(
    kind="drug_targets",
    description=f"{drug.name} acts on {target.symbol} via {mechanism_of_action}",
    metadata={"source": "ChEMBL/Open Targets", "phase": phase, ...}
  ),
]
```

Add a third link describing the inferred pathway context if the target maps to one of the canonical Rett pathways (IGF-1, BDNF, NMDA, sigma-1, KCC2, mitochondrial). For Phase 1 hardcode this mapping in a small dict — pathway curation is not yet a separate concern. **Add a TODO comment** flagging this as something to upgrade in a later phase.

**Logging:** log the top 10 candidates at INFO level when the strategy runs. This is a primary debugging surface during the validation gate.

---

## 10. LangGraph Orchestration

The point of using LangGraph at Phase 1 is structural — it sets up the supervisor → strategies → synthesizer wiring that future phases will populate. Don't skip it just because there's only one strategy.

`src/rett_repurposing/graph/state.py`:

```python
from typing import TypedDict
from rett_repurposing.models import Disease, CandidateList

class RepurposingState(TypedDict):
    disease: Disease
    enabled_strategies: list[str]            # Phase 1: ["target_based"]
    strategy_outputs: dict[str, CandidateList]
    final_candidates: CandidateList | None
    log: list[str]                           # human-readable trace for UI
```

`src/rett_repurposing/graph/supervisor.py` — for Phase 1 the supervisor logic is trivial: read `enabled_strategies`, set up the routing. **Do not** add LLM-based supervision yet; that becomes meaningful in Phase 2+ when there are multiple strategies and the routing decision is non-trivial. A simple deterministic dispatcher is correct here.

`src/rett_repurposing/graph/nodes.py` — implements one node per strategy. Each node reads `disease` from state, runs the strategy, writes the output to `strategy_outputs[strategy.name]`.

`src/rett_repurposing/graph/synthesizer.py` — Phase 1 synthesizer is a passthrough: read the single `CandidateList` from `strategy_outputs`, copy to `final_candidates`. Add a TODO comment noting that Phase 4 introduces real aggregation.

The graph compiles to a single entry point that takes a `Disease` and returns the final `CandidateList`.

---

## 11. FastAPI Backend

`src/rett_repurposing/api/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rett_repurposing.api.routes import router

app = FastAPI(title="Rett Repurposing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
```

`src/rett_repurposing/api/routes.py` — implement two endpoints:

**`GET /health`** — returns `{"status": "ok", "duckdb_ready": <bool>}`. The `duckdb_ready` check confirms the local store exists and has data.

**`POST /repurpose`** — accepts `{"disease": "Rett syndrome"}` (free-text resolved server-side via Open Targets `search` if not already known), returns SSE stream.

SSE event sequence:

```
event: status
data: {"phase": "resolving_disease", "message": "Resolving disease ID..."}

event: status
data: {"phase": "running_strategy", "strategy": "target_based", "message": "Running target-based strategy..."}

event: candidate
data: {<Candidate JSON>}

event: candidate
data: {<Candidate JSON>}

...

event: complete
data: {"total": 50, "strategies_run": ["target_based"]}
```

Stream candidates one-by-one as they're computed, ordered by score descending. Use `sse-starlette`'s `EventSourceResponse`. Set appropriate `Cache-Control: no-cache` headers.

Surface errors as a final `event: error` with `{"message": ..., "phase": ...}` payload before closing the stream.

---

## 12. Next.js Frontend

The frontend is one page. It posts to `/api/repurpose` (a Next.js Route Handler that proxies to FastAPI) and renders a streaming list of candidates.

`frontend/src/app/page.tsx`:

- Header: project name, brief description, link to GitHub repo.
- Disease input (defaulted to "Rett syndrome" — single disease for Phase 1, but treat the input as future-multi-disease).
- "Run analysis" button.
- Streaming candidate list: each candidate renders as a card with drug name, target, score, and an expandable evidence trail.
- A status banner at the top showing the current pipeline phase (resolving → strategy running → complete).

`frontend/src/app/api/repurpose/route.ts` — proxy that opens an SSE connection to FastAPI and re-streams to the browser. Use the Vercel AI SDK's streaming utilities; do not roll your own SSE parsing if the SDK covers it.

`frontend/src/components/candidate-card.tsx` — receives a `Candidate`, renders:

- Rank number (1, 2, 3, ...)
- Drug name (prominent), trade names underneath if any
- Target symbol (smaller)
- Score (with score component breakdown on hover)
- Evidence trail (collapsible, default-collapsed for #4+)

Use shadcn/ui primitives (`Card`, `Badge`, `Collapsible`). Match GMIND's visual sensibility: clean, dense, professional. Light/dark mode supported via `next-themes`.

`frontend/src/lib/types.ts` mirrors the Pydantic models. **Do not auto-generate** the types in Phase 1 — hand-write them to match exactly. (Phase 2+ may introduce OpenAPI codegen.)

---

## 13. Logging & Observability

Use `structlog` configured to emit JSON in production and pretty console in dev (toggle via `ENV` env var). Log at the boundaries:

- Each fetcher call: source, query, duration, response size.
- Each strategy run: name, disease, candidate count, top-10 scores.
- Each API request: route, duration, status.

Do not introduce Langfuse in Phase 1. It's nice-to-have but a distraction at this scale. Add a TODO in `logging.py` noting Langfuse integration is a Phase 2+ concern.

---

## 14. Testing Approach

**Unit tests** (fast, no network):

- `test_models.py` — Pydantic validation behavior on edge cases.
- `test_strategies.py` — `target_based` strategy with hand-crafted in-memory DuckDB fixtures. Verify scoring, sorting, evidence chain construction.
- `test_store.py` — DuckDB schema creation and basic queries against a fresh in-memory database.

**Integration tests** (require recorded fixtures, no live network):

- `test_fetchers.py` — use `vcrpy` or stored JSON fixtures in `tests/fixtures/` to test fetcher parsing without hitting live APIs. Record fixtures once; commit them.
- `test_api.py` — use FastAPI's `TestClient` with a fixture-loaded DuckDB. Test the SSE event sequence.

**Validation tests** (the oracle):

- `test_validation.py` — runs the full pipeline against the actual local DuckDB (skip if `data/rett_repurposing.duckdb` doesn't exist) and asserts that the top 20 candidates contain at least one drug from each of: IGF-1 axis, BDNF/TrkB pathway, NMDA modulator class, sigma-1 agonist class. Curate a small "oracle compounds" list in `tests/fixtures/rett_oracle.json` (drug names and ChEMBL IDs).

This validation test is the single most important test in Phase 1. **Do not consider Phase 1 done until it passes.**

---

## 15. Acceptance Criteria for Phase 1

Phase 1 ships when all of the following are true:

1. `make build && make fetch && make test` passes on a clean checkout (Docker Desktop required).
2. `make up` starts both services cleanly; the frontend at `http://localhost:3000` can hit the backend and stream a candidate list end-to-end.
3. The validation test (`test_validation.py`) passes — at least one oracle compound from each of the four canonical Rett pathway classes appears in the top 20 candidates.
4. The README contains a working "quickstart" section that a stranger can follow to clone and run the system via Docker Compose.
5. `DATA_LICENSES.md` accurately reflects all sources used.
6. CI (GitHub Actions) is configured to run lint, typecheck, and unit/integration tests on PRs. CI runs against host-mode (`uv` + `pnpm`) for speed; Docker build is verified by a separate `docker compose build` job. No need for CI to run the validation test (it requires real data).

---

## 16. Conventions

**Python:**

- All async functions use `async def`. Never mix sync I/O with async code (including in tests — use `pytest-asyncio`).
- Type annotations are mandatory in `src/`. Use `from __future__ import annotations` and modern union syntax (`X | Y`) given Python 3.12.
- Pydantic v2 `BaseModel` subclasses; use `Field(...)` for validation.
- No runtime configuration via globals. Inject config via `pydantic-settings`.
- DuckDB connections are context-managed. Never leak.
- Errors: raise typed exceptions (`OpenTargetsError`, `ChEMBLError`, `StoreError`). Don't bubble raw `httpx.HTTPError`.

**TypeScript:**

- Strict mode on. No `any` without an inline `// reason: ...` justification.
- Server components by default; client components only when interactivity demands it.

**Git:**

- Conventional Commits.
- Each Phase 1 deliverable lands as a separate PR: data layer, strategy, graph, API, frontend. Don't ship one giant PR.

**Documentation:**

- Every module has a module-level docstring stating purpose.
- Every public function has a docstring with Args/Returns/Raises.
- TODO comments include phase: `# TODO(phase-2): replace with hierarchical Bayesian aggregation`.

---

## 17. What to Decide Yourself vs. Ask About

**Decide yourself:**

- Library choices not pinned in §3 (e.g., HTTP retry strategy, JSON serialization helpers).
- Lint and format details (within reason).
- Test fixture organization.
- Error message wording.
- Variable naming.

**Ask before doing:**

- Any deviation from the directory structure in §4.
- Any change to the Pydantic models in §7 (other phases depend on them).
- Any change to the Strategy ABC in §8.
- Adding a new top-level dependency not listed in §3.
- Adding authentication or any user-facing feature beyond the single page in §12.

---

## 18. Out of Scope (Do Not Build in Phase 1)

- Signature reversal strategy (Phase 2)
- Network proximity strategy (Phase 3)
- Bayesian aggregation (Phase 4)
- BioNeMo / DiffDock integration (v1+)
- MCP server wrappers (v1+)
- Temporal workflows (v1+)
- Multi-disease support beyond Rett
- User authentication
- Persistent run history / past results
- Any analytics or telemetry
- Mobile-responsive UI polish (desktop-first is fine)

Flag any of these if you think they're actually needed before Phase 1 can ship — but the default answer is "later."

---

## 19. References (For Your Investigation, Not for Hardcoding)

- Open Targets GraphQL playground: https://api.platform.opentargets.org/api/v4/graphql/browser
- Open Targets API docs: https://platform-docs.opentargets.org/data-access/graphql-api
- ChEMBL REST API: https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services
- LangGraph docs: https://langchain-ai.github.io/langgraph/
- FastAPI SSE: https://github.com/sysid/sse-starlette
- DuckDB Python: https://duckdb.org/docs/clients/python/overview

---

## 20. First Actions

When you start, your first three commits should be:

1. **Repo scaffolding + Docker** — pyproject.toml, uv.lock, frontend skeleton (`pnpm create next-app` with TypeScript + App Router + Tailwind), Makefile, `.env.example`, README stub, both Dockerfiles, `docker-compose.yml`, `docker-compose.override.yml`, `.dockerignore`. Verify `make build` succeeds and `make up` starts both services with placeholder routes. No application code yet beyond a `/health` stub.
2. **Data layer** — fetchers (with VCR-recorded fixtures), DuckDB schema, `build_local_store.py`. Ends with a working `make fetch` populating `./data/rett_repurposing.duckdb`.
3. **Models + target-based strategy** — Pydantic models, Strategy ABC, target_based implementation, unit tests.

After those three, the remaining work (LangGraph wiring, FastAPI, Next.js, validation test) lands incrementally.

Good luck. When in doubt, ship the smallest thing that demonstrates the architecture, then iterate.
