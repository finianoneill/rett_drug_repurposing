"""Strategy nodes for the LangGraph pipeline.

Each node wraps a `Strategy` instance: it reads `disease` from state, calls
`strategy.run(disease)`, and writes the output into `strategy_outputs[name]`.

A node factory pattern keeps the strategy instance closed over the function
so the graph builder can wire in dependencies (DuckDB connection, future
config) at construction time without bleeding them into LangGraph state.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog

from rett_repurposing.graph.state import RepurposingState
from rett_repurposing.strategies.base import Strategy

log = structlog.get_logger(__name__)

NodeFn = Callable[[RepurposingState], Awaitable[dict[str, object]]]


def strategy_node(strategy: Strategy) -> NodeFn:
    """Build an async LangGraph node that runs the given strategy."""

    async def node(state: RepurposingState) -> dict[str, object]:
        disease = state["disease"]
        log.info("strategy_node.start", strategy=strategy.name, efo_id=disease.efo_id)
        result = await strategy.run(disease)
        log.info(
            "strategy_node.done",
            strategy=strategy.name,
            candidate_count=len(result.candidates),
        )
        return {
            "strategy_outputs": {strategy.name: result},
            "log": [f"{strategy.name}: produced {len(result.candidates)} candidates"],
        }

    node.__name__ = f"{strategy.name}_node"
    return node
