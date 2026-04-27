"""Canonical domain models. Other phases import these — field names are stable.

See IMPLEMENTATION_BRIEF.md §7 for the contract.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Disease(BaseModel):
    efo_id: str
    name: str


class Target(BaseModel):
    ensembl_id: str
    symbol: str | None = None
    name: str | None = None
    biotype: str | None = None
    overall_association_score: float | None = Field(default=None, ge=0.0, le=1.0)
    datatype_scores: dict[str, float] = Field(default_factory=dict)


class Drug(BaseModel):
    chembl_id: str
    name: str
    drug_type: str | None = None
    max_phase: float | None = None
    is_approved: bool = False
    first_approval_year: int | None = None
    withdrawn: bool = False
    trade_names: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    canonical_smiles: str | None = None
    atc_classifications: list[str] = Field(default_factory=list)


class EvidenceLink(BaseModel):
    """One link in a candidate's evidence chain."""

    kind: str
    description: str
    metadata: dict[str, str | float | int] = Field(default_factory=dict)


class Candidate(BaseModel):
    """A single repurposing candidate output by a strategy."""

    drug: Drug
    target: Target
    score: float = Field(..., ge=0.0)
    score_components: dict[str, float] = Field(default_factory=dict)
    evidence: list[EvidenceLink]
    strategy: str


class CandidateList(BaseModel):
    disease: Disease
    candidates: list[Candidate]
    strategy: str
    generated_at: datetime
