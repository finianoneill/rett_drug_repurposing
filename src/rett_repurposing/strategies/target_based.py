"""Target-based repurposing strategy — Phase 1.

See IMPLEMENTATION_BRIEF.md §9. Algorithm:

1. Query DuckDB `approved_drugs_for_disease` for the input disease.
2. Compute a per-(drug, target) score = 0.6·target_association + 0.4·norm_drug_evidence,
   where norm_drug_evidence = min(1, log1p(N_evidence) / log1p(MAX_EVIDENCE)).
3. Aggregate: keep the highest-scoring (drug, target) per drug as canonical;
   record alternative targets in evidence.
4. Sort by score descending, return top N.

# TODO(phase-2): replace the hardcoded RETT_PATHWAY_MAP with a curated
# pathway-context layer (Reactome / OmniPath) so this scales to other diseases.
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from typing import Any

import duckdb
import structlog

from rett_repurposing.models import (
    Candidate,
    CandidateList,
    Disease,
    Drug,
    EvidenceLink,
    Target,
)
from rett_repurposing.store.queries import fetch_approved_drugs_for_disease
from rett_repurposing.strategies.base import Strategy

log = structlog.get_logger(__name__)


# Score weighting per §9. If you change these, update the score_components
# entries below to match.
WEIGHT_TARGET_ASSOCIATION = 0.6
WEIGHT_DRUG_EVIDENCE = 0.4

# Saturation point for the drug-evidence component: beyond this many
# (drug, target) rows we don't reward additional mechanisms.
MAX_EVIDENCE = 10

# Pathway hardcoded for Phase 1 — see TODO at top of module.
RETT_PATHWAY_MAP: dict[str, str] = {
    "IGF1": "IGF-1 axis",
    "IGF1R": "IGF-1 axis",
    "IGFBP3": "IGF-1 axis",
    "BDNF": "BDNF / TrkB signaling",
    "NTRK2": "BDNF / TrkB signaling",
    "GRIN1": "NMDA / glutamate balance",
    "GRIN2A": "NMDA / glutamate balance",
    "GRIN2B": "NMDA / glutamate balance",
    "GRIN2C": "NMDA / glutamate balance",
    "GRIN2D": "NMDA / glutamate balance",
    "GRIN3A": "NMDA / glutamate balance",
    "GRIN3B": "NMDA / glutamate balance",
    "SIGMAR1": "Sigma-1 receptor",
    "SLC12A5": "KCC2 / chloride balance",
    "SLC12A2": "NKCC1 / chloride balance",
}


def _normalize_drug_evidence(num_rows: int) -> float:
    """log1p-saturated normalization: more mechanisms hitting the disease →
    more evidence credit, but with diminishing returns past MAX_EVIDENCE."""
    if num_rows <= 0:
        return 0.0
    return min(1.0, math.log1p(num_rows) / math.log1p(MAX_EVIDENCE))


class TargetBasedStrategy(Strategy):
    """Approved-drug-by-target ranking using Open Targets association scores."""

    name = "target_based"

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        top_n: int = 50,
    ) -> None:
        self._conn = conn
        self._top_n = top_n

    async def run(self, disease: Disease) -> CandidateList:
        # DuckDB queries are synchronous and CPU-bound. Wrap so we don't
        # block the event loop when this runs alongside FastAPI handlers.
        rows = await asyncio.to_thread(fetch_approved_drugs_for_disease, self._conn, disease.efo_id)
        log.info(
            "target_based.fetched_rows",
            efo_id=disease.efo_id,
            row_count=len(rows),
        )

        candidates = _build_candidates(rows)
        candidates.sort(key=lambda c: c.score, reverse=True)
        top = candidates[: self._top_n]

        for i, candidate in enumerate(top[:10], start=1):
            log.info(
                "target_based.top",
                rank=i,
                drug=candidate.drug.name,
                target=candidate.target.symbol if candidate.target else None,
                score=round(candidate.score, 4),
            )

        return CandidateList(
            disease=disease,
            candidates=top,
            strategy=self.name,
            generated_at=datetime.now(tz=UTC),
        )


def _build_candidates(rows: list[dict[str, Any]]) -> list[Candidate]:
    """Group rows by drug, score each (drug, target) pair, dedupe to one
    candidate per drug (highest-scoring target as canonical)."""
    by_drug: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_drug.setdefault(row["chembl_id"], []).append(row)

    candidates: list[Candidate] = []
    for chembl_id, drug_rows in by_drug.items():
        norm_evidence = _normalize_drug_evidence(len(drug_rows))
        scored = [(_score_row(r, norm_evidence), r) for r in drug_rows]
        scored.sort(key=lambda x: x[0], reverse=True)
        canonical_score, canonical_row = scored[0]
        alternative_rows = [r for _, r in scored[1:]]

        candidates.append(
            _row_to_candidate(
                canonical_row,
                canonical_score=canonical_score,
                norm_drug_evidence=norm_evidence,
                alternative_rows=alternative_rows,
                evidence_count=len(drug_rows),
            )
        )
        log.debug(
            "target_based.candidate",
            chembl_id=chembl_id,
            evidence_rows=len(drug_rows),
            canonical_target=canonical_row.get("target_symbol"),
            score=round(canonical_score, 4),
        )

    return candidates


def _score_row(row: dict[str, Any], norm_drug_evidence: float) -> float:
    target_assoc = float(row.get("overall_association_score") or 0.0)
    return WEIGHT_TARGET_ASSOCIATION * target_assoc + WEIGHT_DRUG_EVIDENCE * norm_drug_evidence


def _row_to_candidate(
    row: dict[str, Any],
    *,
    canonical_score: float,
    norm_drug_evidence: float,
    alternative_rows: list[dict[str, Any]],
    evidence_count: int,
) -> Candidate:
    target_assoc = float(row.get("overall_association_score") or 0.0)
    target = Target(
        ensembl_id=row["target_ensembl_id"],
        symbol=row.get("target_symbol"),
        name=row.get("target_name"),
        biotype=row.get("biotype"),
        overall_association_score=target_assoc,
        datatype_scores=row.get("datatype_scores") or {},
    )
    drug = Drug(
        chembl_id=row["chembl_id"],
        name=row.get("name") or row["chembl_id"],
        first_approval_year=row.get("first_approval_year"),
        is_approved=True,
    )

    score_components = {
        "target_association": target_assoc,
        "normalized_drug_evidence": norm_drug_evidence,
        "weighted_target_association": WEIGHT_TARGET_ASSOCIATION * target_assoc,
        "weighted_drug_evidence": WEIGHT_DRUG_EVIDENCE * norm_drug_evidence,
        "evidence_row_count": float(evidence_count),
    }

    evidence = _build_evidence_chain(row, alternative_rows)

    return Candidate(
        drug=drug,
        target=target,
        score=canonical_score,
        score_components=score_components,
        evidence=evidence,
        strategy="target_based",
    )


def _build_evidence_chain(
    row: dict[str, Any],
    alternative_rows: list[dict[str, Any]],
) -> list[EvidenceLink]:
    target_symbol = row.get("target_symbol") or row["target_ensembl_id"]
    drug_name = row.get("name") or row["chembl_id"]
    target_assoc = float(row.get("overall_association_score") or 0.0)
    mechanism = row.get("mechanism_of_action") or "(mechanism unspecified)"
    phase = row.get("phase")
    ct_ids = row.get("ct_ids") or []

    chain: list[EvidenceLink] = [
        EvidenceLink(
            kind="target_associated_with_disease",
            description=(
                f"{target_symbol} is associated with the disease "
                f"(Open Targets score: {target_assoc:.2f})"
            ),
            metadata={
                "source": "Open Targets",
                "score": target_assoc,
                "target_ensembl_id": row["target_ensembl_id"],
            },
        ),
        EvidenceLink(
            kind="drug_targets",
            description=f"{drug_name} acts on {target_symbol} via {mechanism}",
            metadata={
                "source": "ChEMBL/Open Targets",
                "phase": float(phase) if phase is not None else 0.0,
                "ct_ids": ",".join(ct_ids) if ct_ids else "",
            },
        ),
    ]

    if pathway := RETT_PATHWAY_MAP.get(target_symbol or ""):
        chain.append(
            EvidenceLink(
                kind="pathway_context",
                description=f"{target_symbol} sits in the {pathway} pathway",
                metadata={"source": "curated", "pathway": pathway},
            )
        )

    if alternative_rows:
        alt_descriptions = [
            f"{alt.get('target_symbol') or alt['target_ensembl_id']} ({alt.get('mechanism_of_action') or '?'})"
            for alt in alternative_rows[:5]
        ]
        chain.append(
            EvidenceLink(
                kind="alternative_targets",
                description=(
                    f"{drug_name} also engages {len(alternative_rows)} other "
                    f"disease-associated target(s): {', '.join(alt_descriptions)}"
                ),
                metadata={
                    "source": "Open Targets",
                    "alternative_count": len(alternative_rows),
                },
            )
        )

    return chain
