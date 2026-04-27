"""LangGraph wiring tests.

The supervisor → strategy → synthesizer path is deterministic in Phase 1.
We exercise it end-to-end with an in-memory DuckDB and a small dataset.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rett_repurposing.graph import build_graph, build_strategies
from rett_repurposing.models import Disease
from rett_repurposing.store.queries import (
    upsert_disease,
    upsert_disease_target,
    upsert_drug,
    upsert_drug_target_disease,
)

EFO = "MONDO_TEST"
DISEASE = Disease(efo_id=EFO, name="Test disease")


def _seed_minimal(conn) -> None:
    upsert_disease(conn, efo_id=EFO, name="Test disease", fetched_at=datetime.now(tz=UTC))
    upsert_disease_target(
        conn,
        efo_id=EFO,
        target_ensembl_id="ENSG_TEST",
        target_symbol="GRIN1",
        target_name="N-methyl-D-aspartate receptor 1",
        biotype="protein_coding",
        overall_association_score=0.42,
        datatype_scores={"literature": 0.6},
    )
    upsert_drug(
        conn,
        chembl_id="CHEMBL_TEST",
        name="TestDrug",
        drug_type="Small molecule",
        max_phase=4.0,
        is_approved=True,
        first_approval_year=2010,
        withdrawn_flag=False,
        trade_names=[],
        synonyms=[],
        canonical_smiles=None,
        atc_classifications=[],
    )
    upsert_drug_target_disease(
        conn,
        chembl_id="CHEMBL_TEST",
        target_ensembl_id="ENSG_TEST",
        efo_id=EFO,
        phase=4.0,
        status="Completed",
        mechanism_of_action="NMDA receptor antagonist",
        ct_ids=["NCT_TEST"],
    )


@pytest.mark.asyncio
async def test_graph_runs_target_based_end_to_end(memory_db):
    _seed_minimal(memory_db)
    graph = build_graph(build_strategies(memory_db))

    result = await graph.ainvoke(
        {
            "disease": DISEASE,
            "enabled_strategies": ["target_based"],
            "strategy_outputs": {},
            "final_candidates": None,
            "log": [],
        }
    )

    assert result["final_candidates"] is not None
    final = result["final_candidates"]
    assert final.strategy == "target_based"
    assert len(final.candidates) == 1
    assert final.candidates[0].drug.chembl_id == "CHEMBL_TEST"

    # `strategy_outputs` carries the per-strategy result the synthesizer copied from.
    assert "target_based" in result["strategy_outputs"]


@pytest.mark.asyncio
async def test_graph_log_accumulates_each_node(memory_db):
    _seed_minimal(memory_db)
    graph = build_graph(build_strategies(memory_db))

    result = await graph.ainvoke(
        {
            "disease": DISEASE,
            "enabled_strategies": ["target_based"],
            "strategy_outputs": {},
            "final_candidates": None,
            "log": [],
        }
    )

    log = result["log"]
    assert any("supervisor" in entry for entry in log)
    assert any("target_based" in entry for entry in log)
    assert any("synthesizer" in entry for entry in log)


@pytest.mark.asyncio
async def test_empty_enabled_strategies_short_circuits(memory_db):
    _seed_minimal(memory_db)
    graph = build_graph(build_strategies(memory_db))

    result = await graph.ainvoke(
        {
            "disease": DISEASE,
            "enabled_strategies": [],
            "strategy_outputs": {},
            "final_candidates": None,
            "log": [],
        }
    )

    # No strategies ran; synthesizer logs the empty-input warning and leaves
    # final_candidates unset.
    assert result["final_candidates"] is None
    assert any("no strategy outputs" in entry for entry in result["log"])
