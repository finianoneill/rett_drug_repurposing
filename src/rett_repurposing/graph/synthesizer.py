"""Synthesizer node — Phase 1 passthrough.

# TODO(phase-4): replace with hierarchical Bayesian aggregation across multiple
# strategy outputs. For Phase 1, exactly one strategy runs and its CandidateList
# is copied verbatim into `final_candidates`.
"""

from __future__ import annotations

import structlog

from rett_repurposing.graph.state import RepurposingState
from rett_repurposing.models import CandidateList

log = structlog.get_logger(__name__)


def synthesizer(state: RepurposingState) -> dict[str, object]:
    outputs = state.get("strategy_outputs") or {}
    if not outputs:
        log.warning("synthesizer.no_outputs")
        return {
            "final_candidates": None,
            "log": ["synthesizer: no strategy outputs to synthesize"],
        }

    if len(outputs) > 1:
        # Phase 1 should never hit this path; if it does, surface it loudly
        # and pick the first deterministically (alphabetical) so behaviour
        # is reproducible until Phase 4 lands real aggregation.
        log.warning(
            "synthesizer.multiple_outputs.passthrough",
            strategies=sorted(outputs.keys()),
        )
        first_key = sorted(outputs.keys())[0]
        chosen: CandidateList = outputs[first_key]
    else:
        first_key = next(iter(outputs.keys()))
        chosen = outputs[first_key]

    log.info(
        "synthesizer.passthrough",
        strategy=first_key,
        candidate_count=len(chosen.candidates),
    )
    return {
        "final_candidates": chosen,
        "log": [f"synthesizer: passthrough from strategy={first_key}"],
    }
