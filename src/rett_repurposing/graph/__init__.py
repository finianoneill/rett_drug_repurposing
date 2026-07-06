"""LangGraph orchestration. See IMPLEMENTATION_BRIEF.md §10.

The compiled graph takes a `Disease` (plus a list of enabled strategy names)
and returns a `CandidateList`. The shape is deliberately overspecified for
Phase 1's single strategy so Phase 2+ can add strategies without rewiring.

Layout:

    START → supervisor ──conditional──► target_based ──► synthesizer → END

Future strategy nodes plug in as additional conditional-edge destinations
fanning out from the supervisor.
"""

from __future__ import annotations

from collections.abc import Hashable

import duckdb
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from rett_repurposing.graph.nodes import strategy_node
from rett_repurposing.graph.state import RepurposingState
from rett_repurposing.graph.supervisor import route_to_strategies, supervisor
from rett_repurposing.graph.synthesizer import synthesizer
from rett_repurposing.strategies.base import Strategy
from rett_repurposing.strategies.signature_reversal import SignatureReversalStrategy
from rett_repurposing.strategies.target_based import TargetBasedStrategy

__all__ = [
    "RepurposingState",
    "build_graph",
    "build_strategies",
]


def build_strategies(conn: duckdb.DuckDBPyConnection) -> dict[str, Strategy]:
    """Construct the strategy registry.

    Phase 1 shipped ``target_based``; Phase 2 adds ``signature_reversal``. Both
    plug into the same supervisor fan-out — callers pick which run via
    ``enabled_strategies``.
    """
    return {
        "target_based": TargetBasedStrategy(conn),
        "signature_reversal": SignatureReversalStrategy(conn),
    }


def build_graph(
    strategies: dict[str, Strategy],
) -> CompiledStateGraph[RepurposingState, None, RepurposingState, RepurposingState]:
    """Compile the LangGraph pipeline with the given strategy registry.

    Each strategy's `name` becomes the node name. The supervisor's conditional
    edges fan out to whichever strategy names appear in `enabled_strategies`.
    """
    graph: StateGraph[RepurposingState, None, RepurposingState, RepurposingState] = StateGraph(
        RepurposingState
    )

    graph.add_node("supervisor", supervisor)
    graph.add_node("synthesizer", synthesizer)

    for name, strategy in strategies.items():
        # LangGraph's add_node type stubs don't model async nodes cleanly;
        # they're supported at runtime via Runnable adaptation.
        graph.add_node(name, strategy_node(strategy))  # type: ignore[arg-type]
        graph.add_edge(name, "synthesizer")

    graph.add_edge(START, "supervisor")
    # Path map needs every possible destination the router can return.
    path_map: dict[Hashable, str] = {
        **{name: name for name in strategies},
        "synthesizer": "synthesizer",
    }
    graph.add_conditional_edges("supervisor", route_to_strategies, path_map)
    graph.add_edge("synthesizer", END)

    return graph.compile()
