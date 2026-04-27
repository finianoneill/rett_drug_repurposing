"""Target-based strategy behavior against hand-crafted in-memory DuckDB."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rett_repurposing.models import Disease
from rett_repurposing.store.queries import (
    upsert_disease,
    upsert_disease_target,
    upsert_drug,
    upsert_drug_target_disease,
)
from rett_repurposing.strategies.target_based import (
    MAX_EVIDENCE,
    WEIGHT_DRUG_EVIDENCE,
    WEIGHT_TARGET_ASSOCIATION,
    TargetBasedStrategy,
    _normalize_drug_evidence,
)

EFO = "MONDO_0010726"
DISEASE = Disease(efo_id=EFO, name="Rett syndrome")


def _seed_disease(conn):
    upsert_disease(conn, efo_id=EFO, name="Rett syndrome", fetched_at=datetime.now(tz=UTC))


def _seed_target(
    conn,
    *,
    ensembl_id: str,
    symbol: str,
    score: float,
    datatype_scores: dict[str, float] | None = None,
) -> None:
    upsert_disease_target(
        conn,
        efo_id=EFO,
        target_ensembl_id=ensembl_id,
        target_symbol=symbol,
        target_name=f"{symbol} name",
        biotype="protein_coding",
        overall_association_score=score,
        datatype_scores=datatype_scores or {},
    )


def _seed_drug(conn, chembl_id: str, name: str) -> None:
    upsert_drug(
        conn,
        chembl_id=chembl_id,
        name=name,
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


def _seed_link(
    conn,
    *,
    chembl_id: str,
    target_id: str,
    mechanism: str,
    phase: float = 4.0,
    ct_ids: list[str] | None = None,
) -> None:
    upsert_drug_target_disease(
        conn,
        chembl_id=chembl_id,
        target_ensembl_id=target_id,
        efo_id=EFO,
        phase=phase,
        status="Completed",
        mechanism_of_action=mechanism,
        ct_ids=ct_ids or [],
    )


def test_normalize_drug_evidence():
    assert _normalize_drug_evidence(0) == 0.0
    assert _normalize_drug_evidence(1) == pytest.approx(0.288, rel=1e-2)
    assert _normalize_drug_evidence(MAX_EVIDENCE) == 1.0
    assert _normalize_drug_evidence(MAX_EVIDENCE + 5) == 1.0


@pytest.mark.asyncio
async def test_returns_one_candidate_per_drug(memory_db):
    _seed_disease(memory_db)
    _seed_target(memory_db, ensembl_id="ENSG_GRIN1", symbol="GRIN1", score=0.3)
    _seed_target(memory_db, ensembl_id="ENSG_GRIN2A", symbol="GRIN2A", score=0.6)
    _seed_drug(memory_db, "CHEMBL_KETAMINE", "KETAMINE")
    _seed_link(
        memory_db,
        chembl_id="CHEMBL_KETAMINE",
        target_id="ENSG_GRIN1",
        mechanism="NMDA negative allosteric modulator",
    )
    _seed_link(
        memory_db,
        chembl_id="CHEMBL_KETAMINE",
        target_id="ENSG_GRIN2A",
        mechanism="NMDA negative allosteric modulator",
    )

    strategy = TargetBasedStrategy(memory_db)
    result = await strategy.run(DISEASE)

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    # Canonical target should be GRIN2A (higher association score).
    assert candidate.target.symbol == "GRIN2A"
    # An alternative_targets evidence link should mention GRIN1.
    alt_links = [e for e in candidate.evidence if e.kind == "alternative_targets"]
    assert len(alt_links) == 1
    assert "GRIN1" in alt_links[0].description


@pytest.mark.asyncio
async def test_score_formula_matches_brief(memory_db):
    _seed_disease(memory_db)
    _seed_target(memory_db, ensembl_id="ENSG_T1", symbol="GRIN1", score=0.5)
    _seed_drug(memory_db, "CHEMBL_DRUG", "DRUG")
    _seed_link(memory_db, chembl_id="CHEMBL_DRUG", target_id="ENSG_T1", mechanism="agonist")

    strategy = TargetBasedStrategy(memory_db)
    result = await strategy.run(DISEASE)

    candidate = result.candidates[0]
    norm_evidence = _normalize_drug_evidence(1)
    expected = WEIGHT_TARGET_ASSOCIATION * 0.5 + WEIGHT_DRUG_EVIDENCE * norm_evidence
    assert candidate.score == pytest.approx(expected, rel=1e-6)
    assert candidate.score_components["target_association"] == 0.5
    assert candidate.score_components["normalized_drug_evidence"] == pytest.approx(norm_evidence)
    assert candidate.score_components["evidence_row_count"] == 1.0


@pytest.mark.asyncio
async def test_candidates_sorted_descending(memory_db):
    _seed_disease(memory_db)
    _seed_target(memory_db, ensembl_id="ENSG_LO", symbol="LO", score=0.1)
    _seed_target(memory_db, ensembl_id="ENSG_HI", symbol="GRIN1", score=0.9)
    _seed_drug(memory_db, "CHEMBL_LO", "LowDrug")
    _seed_drug(memory_db, "CHEMBL_HI", "HighDrug")
    _seed_link(memory_db, chembl_id="CHEMBL_LO", target_id="ENSG_LO", mechanism="agonist")
    _seed_link(memory_db, chembl_id="CHEMBL_HI", target_id="ENSG_HI", mechanism="agonist")

    strategy = TargetBasedStrategy(memory_db)
    result = await strategy.run(DISEASE)

    assert [c.drug.chembl_id for c in result.candidates] == ["CHEMBL_HI", "CHEMBL_LO"]
    assert result.candidates[0].score > result.candidates[1].score


@pytest.mark.asyncio
async def test_pathway_context_link_for_known_target(memory_db):
    _seed_disease(memory_db)
    _seed_target(memory_db, ensembl_id="ENSG_IGF1R", symbol="IGF1R", score=0.5)
    _seed_drug(memory_db, "CHEMBL_MECASERMIN", "MECASERMIN")
    _seed_link(
        memory_db,
        chembl_id="CHEMBL_MECASERMIN",
        target_id="ENSG_IGF1R",
        mechanism="IGF-1R agonist",
    )

    strategy = TargetBasedStrategy(memory_db)
    result = await strategy.run(DISEASE)

    candidate = result.candidates[0]
    pathway_links = [e for e in candidate.evidence if e.kind == "pathway_context"]
    assert len(pathway_links) == 1
    assert "IGF-1 axis" in pathway_links[0].description


@pytest.mark.asyncio
async def test_pathway_context_omitted_for_unknown_target(memory_db):
    _seed_disease(memory_db)
    _seed_target(memory_db, ensembl_id="ENSG_X", symbol="UNKNOWN_GENE", score=0.4)
    _seed_drug(memory_db, "CHEMBL_X", "DRUG_X")
    _seed_link(memory_db, chembl_id="CHEMBL_X", target_id="ENSG_X", mechanism="modulator")

    strategy = TargetBasedStrategy(memory_db)
    result = await strategy.run(DISEASE)

    candidate = result.candidates[0]
    pathway_links = [e for e in candidate.evidence if e.kind == "pathway_context"]
    assert len(pathway_links) == 0


@pytest.mark.asyncio
async def test_evidence_chain_has_target_and_drug_links(memory_db):
    _seed_disease(memory_db)
    _seed_target(memory_db, ensembl_id="ENSG_T", symbol="T", score=0.3)
    _seed_drug(memory_db, "CHEMBL_D", "DRUG")
    _seed_link(
        memory_db, chembl_id="CHEMBL_D", target_id="ENSG_T", mechanism="agonist", ct_ids=["NCT0001"]
    )

    strategy = TargetBasedStrategy(memory_db)
    result = await strategy.run(DISEASE)

    kinds = [e.kind for e in result.candidates[0].evidence]
    assert "target_associated_with_disease" in kinds
    assert "drug_targets" in kinds


@pytest.mark.asyncio
async def test_top_n_truncation(memory_db):
    _seed_disease(memory_db)
    for i in range(5):
        target_id = f"ENSG_T{i}"
        _seed_target(memory_db, ensembl_id=target_id, symbol=f"T{i}", score=0.1 * i)
        _seed_drug(memory_db, f"CHEMBL_{i}", f"D{i}")
        _seed_link(memory_db, chembl_id=f"CHEMBL_{i}", target_id=target_id, mechanism="m")

    strategy = TargetBasedStrategy(memory_db, top_n=3)
    result = await strategy.run(DISEASE)

    assert len(result.candidates) == 3


@pytest.mark.asyncio
async def test_strategy_name_and_metadata(memory_db):
    _seed_disease(memory_db)
    strategy = TargetBasedStrategy(memory_db)
    assert strategy.name == "target_based"
    result = await strategy.run(DISEASE)
    assert result.strategy == "target_based"
    assert result.disease == DISEASE
    assert result.candidates == []
