"""Shared state for the LangGraph pipeline. See IMPLEMENTATION_BRIEF.md §10.

`strategy_outputs` and `log` carry reducers so multiple strategy nodes can
write concurrently without clobbering each other when Phase 2 adds parallel
strategies.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict

from rett_repurposing.models import CandidateList, Disease


def _merge_strategy_outputs(
    left: dict[str, CandidateList],
    right: dict[str, CandidateList],
) -> dict[str, CandidateList]:
    """Reducer for the strategy_outputs map. Right wins on key collisions."""
    return {**left, **right}


class RepurposingState(TypedDict, total=False):
    """LangGraph-managed state.

    `total=False` lets the supervisor seed only the inputs (`disease`,
    `enabled_strategies`); the rest are populated by downstream nodes.
    """

    disease: Disease
    enabled_strategies: list[str]
    strategy_outputs: Annotated[dict[str, CandidateList], _merge_strategy_outputs]
    final_candidates: CandidateList | None
    log: Annotated[list[str], add]
