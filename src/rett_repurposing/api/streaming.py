"""SSE event helpers — formats payloads for `sse-starlette`'s EventSourceResponse.

The exact event names and JSON shapes are part of the API contract documented
in IMPLEMENTATION_BRIEF.md §11. The frontend's TypeScript `lib/types.ts`
mirrors these — keep them in sync.
"""

from __future__ import annotations

import json
from typing import Any

from rett_repurposing.models import Candidate


def status_event(phase: str, message: str, **extra: Any) -> dict[str, str]:
    """Pipeline progress notification."""
    return {
        "event": "status",
        "data": json.dumps({"phase": phase, "message": message, **extra}),
    }


def candidate_event(candidate: Candidate) -> dict[str, str]:
    """One candidate in the result stream. Shape matches `Candidate` Pydantic model."""
    return {
        "event": "candidate",
        "data": candidate.model_dump_json(),
    }


def complete_event(total: int, strategies_run: list[str]) -> dict[str, str]:
    """Terminal success event."""
    return {
        "event": "complete",
        "data": json.dumps({"total": total, "strategies_run": strategies_run}),
    }


def error_event(message: str, phase: str) -> dict[str, str]:
    """Terminal error event. Closes the stream."""
    return {
        "event": "error",
        "data": json.dumps({"message": message, "phase": phase}),
    }
