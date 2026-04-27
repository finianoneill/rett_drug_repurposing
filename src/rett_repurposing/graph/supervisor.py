"""Supervisor node — Phase 1 is a deterministic dispatcher.

# TODO(phase-2): introduce LLM-based supervision when there are multiple
# strategies and the routing decision becomes non-trivial. For Phase 1 the
# routing logic is "run every strategy in `enabled_strategies`".
"""

from __future__ import annotations

import structlog

from rett_repurposing.graph.state import RepurposingState

log = structlog.get_logger(__name__)


def supervisor(state: RepurposingState) -> dict[str, list[str]]:
    """Log the dispatch decision and return state delta with a log entry.

    Routing itself is performed by `route_to_strategies` on the conditional
    edge — this node only records intent.
    """
    enabled = state.get("enabled_strategies", [])
    log.info("supervisor.dispatch", enabled_strategies=enabled)
    return {
        "log": [f"supervisor: dispatching strategies={enabled}"],
    }


def route_to_strategies(state: RepurposingState) -> list[str]:
    """Conditional-edge router. Returns node names to dispatch to in parallel.

    Returning a list lets LangGraph fan out to every enabled strategy node.
    Empty list short-circuits to the synthesizer.
    """
    enabled = state.get("enabled_strategies", [])
    if not enabled:
        return ["synthesizer"]
    return list(enabled)
