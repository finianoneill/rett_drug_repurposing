"""HTTP routes for the repurposing API.

Phase 1 stub: only `/health` is implemented. The `/repurpose` SSE endpoint
lands with the FastAPI commit (see IMPLEMENTATION_BRIEF.md §11).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from rett_repurposing.config import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    duckdb_ready: bool


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness + DuckDB readiness probe."""
    settings = get_settings()
    duckdb_ready = settings.duckdb_path.exists() and settings.duckdb_path.stat().st_size > 0
    return HealthResponse(status="ok", duckdb_ready=duckdb_ready)
