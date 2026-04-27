"""Pydantic validation behavior for the canonical models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from rett_repurposing.models import (
    Candidate,
    CandidateList,
    Disease,
    Drug,
    EvidenceLink,
    Target,
)


def _make_target(score: float | None = 0.5) -> Target:
    return Target(
        ensembl_id="ENSG_T1",
        symbol="T1",
        overall_association_score=score,
    )


def _make_drug() -> Drug:
    return Drug(chembl_id="CHEMBL_X", name="Drug X")


def test_target_score_must_be_in_unit_range():
    with pytest.raises(ValidationError):
        Target(ensembl_id="X", overall_association_score=1.5)
    with pytest.raises(ValidationError):
        Target(ensembl_id="X", overall_association_score=-0.1)


def test_target_score_can_be_none():
    target = Target(ensembl_id="X", overall_association_score=None)
    assert target.overall_association_score is None


def test_drug_defaults():
    d = _make_drug()
    assert d.is_approved is False
    assert d.withdrawn is False
    assert d.trade_names == []
    assert d.synonyms == []
    assert d.atc_classifications == []


def test_candidate_score_must_be_nonnegative():
    with pytest.raises(ValidationError):
        Candidate(
            drug=_make_drug(),
            target=_make_target(),
            score=-0.1,
            evidence=[],
            strategy="target_based",
        )


def test_candidate_score_zero_is_allowed():
    c = Candidate(
        drug=_make_drug(),
        target=_make_target(),
        score=0.0,
        evidence=[],
        strategy="target_based",
    )
    assert c.score == 0.0


def test_evidence_link_metadata_accepts_mixed_scalars():
    link = EvidenceLink(
        kind="drug_targets",
        description="X targets Y",
        metadata={"source": "Open Targets", "score": 0.7, "phase": 4},
    )
    assert link.metadata["source"] == "Open Targets"
    assert link.metadata["score"] == 0.7
    assert link.metadata["phase"] == 4


def test_candidate_list_round_trip():
    disease = Disease(efo_id="MONDO_0010726", name="Rett syndrome")
    candidate = Candidate(
        drug=_make_drug(),
        target=_make_target(),
        score=0.4,
        score_components={"a": 0.1, "b": 0.3},
        evidence=[
            EvidenceLink(kind="k", description="d", metadata={"x": 1.0}),
        ],
        strategy="target_based",
    )
    cl = CandidateList(
        disease=disease,
        candidates=[candidate],
        strategy="target_based",
        generated_at=datetime.now(tz=UTC),
    )
    serialized = cl.model_dump_json()
    restored = CandidateList.model_validate_json(serialized)
    assert restored.disease.efo_id == disease.efo_id
    assert restored.candidates[0].score == 0.4
