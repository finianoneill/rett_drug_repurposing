"""HTTP routes for the repurposing API.

Phase 1 surface:
  GET  /health     — liveness + DuckDB readiness.
  POST /repurpose  — SSE-streamed candidate list. See IMPLEMENTATION_BRIEF.md §11.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from rett_repurposing.api.streaming import (
    candidate_event,
    complete_event,
    error_event,
    status_event,
)
from rett_repurposing.config import get_settings
from rett_repurposing.exceptions import (
    OpenTargetsError,
    RepurposingError,
    StoreError,
)
from rett_repurposing.fetchers.opentargets import OpenTargetsClient
from rett_repurposing.graph import build_graph, build_strategies
from rett_repurposing.models import CandidateList, Disease
from rett_repurposing.store.connection import get_connection

router = APIRouter()
log = structlog.get_logger(__name__)


class HealthResponse(BaseModel):
    status: str
    duckdb_ready: bool


class RepurposeRequest(BaseModel):
    disease: str = Field(..., description="Free-text disease name (resolved server-side).")
    enabled_strategies: list[str] = Field(
        default_factory=lambda: ["target_based"],
        description="Strategy names to run. Phase 1 supports only 'target_based'.",
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness + DuckDB readiness probe."""
    settings = get_settings()
    duckdb_ready = settings.duckdb_path.exists() and settings.duckdb_path.stat().st_size > 0
    return HealthResponse(status="ok", duckdb_ready=duckdb_ready)


@router.post("/repurpose")
async def repurpose(request: RepurposeRequest) -> EventSourceResponse:
    """Run the repurposing pipeline and stream candidates as SSE events."""
    return EventSourceResponse(
        _stream_repurpose(request.disease, request.enabled_strategies),
        headers={"Cache-Control": "no-cache"},
        ping=15,
    )


async def _stream_repurpose(
    disease_query: str,
    enabled_strategies: list[str],
) -> AsyncIterator[dict[str, str]]:
    settings = get_settings()
    log.info(
        "repurpose.start",
        disease=disease_query,
        enabled_strategies=enabled_strategies,
    )

    yield status_event(
        "resolving_disease",
        f"Resolving disease '{disease_query}'...",
    )

    try:
        disease = await _resolve_disease(disease_query, settings.duckdb_path)
    except OpenTargetsError as exc:
        yield error_event(str(exc), "resolving_disease")
        return
    except StoreError as exc:
        yield error_event(str(exc), "resolving_disease")
        return

    yield status_event(
        "disease_resolved",
        f"Resolved to {disease.name} ({disease.efo_id})",
        efo_id=disease.efo_id,
        name=disease.name,
    )

    yield status_event(
        "running_strategy",
        f"Running strategies: {', '.join(enabled_strategies)}",
        strategies=enabled_strategies,
    )

    try:
        final = await _run_pipeline(disease, enabled_strategies, settings.duckdb_path)
    except StoreError as exc:
        yield error_event(str(exc), "running_strategy")
        return
    except RepurposingError as exc:
        yield error_event(str(exc), "running_strategy")
        return
    except Exception as exc:
        log.exception("repurpose.unexpected_error")
        yield error_event(f"unexpected error: {exc}", "running_strategy")
        return

    if final is None:
        yield error_event("Pipeline produced no candidates", "running_strategy")
        return

    for candidate in final.candidates:
        yield candidate_event(candidate)

    yield complete_event(len(final.candidates), enabled_strategies)
    log.info(
        "repurpose.done",
        disease=disease.name,
        candidate_count=len(final.candidates),
    )


async def _resolve_disease(query: str, duckdb_path: Path) -> Disease:
    """Resolve a free-text or EFO-ID disease query.

    Prefers the local store (already-fetched diseases match instantly). Falls
    back to the Open Targets `search` resolver, which requires network.
    """
    if duckdb_path.exists() and duckdb_path.stat().st_size > 0:
        with get_connection(duckdb_path, read_only=True) as conn:
            row = conn.execute(
                """
                SELECT efo_id, name FROM diseases
                WHERE efo_id = ? OR LOWER(name) = LOWER(?)
                LIMIT 1
                """,
                [query, query],
            ).fetchone()
        if row is not None:
            efo_id, name = row
            return Disease(efo_id=efo_id, name=name)

    async with OpenTargetsClient() as client:
        efo_id, name = await client.resolve_disease_id(query)
    return Disease(efo_id=efo_id, name=name)


async def _run_pipeline(
    disease: Disease,
    enabled_strategies: list[str],
    duckdb_path: Path,
) -> CandidateList | None:
    """Compile the graph against a per-request connection and invoke it."""
    with get_connection(duckdb_path, read_only=True) as conn:
        graph = build_graph(build_strategies(conn))
        result = await graph.ainvoke(
            {
                "disease": disease,
                "enabled_strategies": enabled_strategies,
                "strategy_outputs": {},
                "final_candidates": None,
                "log": [],
            }
        )
    final = result.get("final_candidates")
    if final is None:
        return None
    if not isinstance(final, CandidateList):
        # Defensive: graph contract returns CandidateList | None.
        return None
    return final
