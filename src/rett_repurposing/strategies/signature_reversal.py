"""Signature-reversal repurposing strategy — Phase 2.

See docs/rett-repurposing-design-doc.md §5. Where the target-based strategy asks
"what approved drug hits a Rett-associated target?", signature reversal asks
"what drug's transcriptional effect *undoes* the Rett expression signature?".
It catches candidates whose mechanism is unclear or target-agnostic.

Algorithm:

1. A Rett disease signature (top up/down human genes) was derived from
   Mecp2-null mouse cortex RNA-seq (see ``rett_repurposing.signature``).
2. SigCom LINCS scored every L1000 chemical perturbagen for how strongly it
   reverses that signature; reversers were resolved to ChEMBL and aggregated to
   the strongest reversing signature per drug (``drug_signature_reversal``).
3. This strategy reads those pre-computed reversal scores, normalises them to
   [0, 1], and emits candidates ordered by reversal strength.

Candidates are target-agnostic — ``Candidate.target`` is ``None``.
"""

from __future__ import annotations

import asyncio
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
)
from rett_repurposing.store.queries import (
    fetch_disease_signature,
    fetch_signature_reversal_candidates,
)
from rett_repurposing.strategies.base import Strategy

log = structlog.get_logger(__name__)


class SignatureReversalStrategy(Strategy):
    """Rank drugs by how strongly their L1000 signature reverses Rett's."""

    name = "signature_reversal"

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        top_n: int = 50,
    ) -> None:
        self._conn = conn
        self._top_n = top_n

    async def run(self, disease: Disease) -> CandidateList:
        rows = await asyncio.to_thread(
            fetch_signature_reversal_candidates, self._conn, disease.efo_id
        )
        signature = await asyncio.to_thread(fetch_disease_signature, self._conn, disease.efo_id)
        source = await asyncio.to_thread(self._signature_source, disease.efo_id)
        n_signature_genes = len(signature.get("up", [])) + len(signature.get("down", []))

        log.info(
            "signature_reversal.fetched_rows",
            efo_id=disease.efo_id,
            row_count=len(rows),
            signature_genes=n_signature_genes,
        )

        candidates = _build_candidates(rows, source=source, n_signature_genes=n_signature_genes)
        candidates.sort(key=lambda c: c.score, reverse=True)
        top = candidates[: self._top_n]

        for i, candidate in enumerate(top[:10], start=1):
            log.info(
                "signature_reversal.top",
                rank=i,
                drug=candidate.drug.name,
                reversal_score=round(candidate.score_components.get("reversal_score", 0.0), 3),
                score=round(candidate.score, 4),
            )

        return CandidateList(
            disease=disease,
            candidates=top,
            strategy=self.name,
            generated_at=datetime.now(tz=UTC),
        )

    def _signature_source(self, efo_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT source FROM disease_signature WHERE efo_id = ? AND source IS NOT NULL LIMIT 1",
            [efo_id],
        ).fetchone()
        return str(row[0]) if row and row[0] is not None else None


def _build_candidates(
    rows: list[dict[str, Any]],
    *,
    source: str | None,
    n_signature_genes: int,
) -> list[Candidate]:
    """Convert reversal rows to candidates, normalising scores to [0, 1]."""
    if not rows:
        return []

    max_reversal = max((float(r.get("reversal_score") or 0.0) for r in rows), default=0.0)
    denom = max_reversal if max_reversal > 0 else 1.0

    candidates: list[Candidate] = []
    for row in rows:
        reversal_score = float(row.get("reversal_score") or 0.0)
        candidates.append(
            _row_to_candidate(
                row,
                normalized_score=reversal_score / denom,
                reversal_score=reversal_score,
                source=source,
                n_signature_genes=n_signature_genes,
            )
        )
    return candidates


def _row_to_candidate(
    row: dict[str, Any],
    *,
    normalized_score: float,
    reversal_score: float,
    source: str | None,
    n_signature_genes: int,
) -> Candidate:
    z_up = _as_float(row.get("z_up"))
    z_down = _as_float(row.get("z_down"))
    z_sum = _as_float(row.get("z_sum"))
    n_signatures = int(row.get("n_signatures") or 0)

    drug = Drug(
        chembl_id=row["chembl_id"],
        name=row.get("name") or row["chembl_id"],
        first_approval_year=row.get("first_approval_year"),
        is_approved=bool(row.get("is_approved")),
    )

    score_components = {
        "reversal_score": reversal_score,
        "z_up": z_up if z_up is not None else 0.0,
        "z_down": z_down if z_down is not None else 0.0,
        "z_sum": z_sum if z_sum is not None else 0.0,
        "signatures_supporting": float(n_signatures),
    }

    return Candidate(
        drug=drug,
        target=None,
        score=normalized_score,
        score_components=score_components,
        evidence=_build_evidence_chain(
            row,
            z_up=z_up,
            z_down=z_down,
            n_signatures=n_signatures,
            source=source,
            n_signature_genes=n_signature_genes,
        ),
        strategy="signature_reversal",
    )


def _build_evidence_chain(
    row: dict[str, Any],
    *,
    z_up: float | None,
    z_down: float | None,
    n_signatures: int,
    source: str | None,
    n_signature_genes: int,
) -> list[EvidenceLink]:
    drug_name = row.get("name") or row["chembl_id"]
    pert_name = row.get("pert_name") or drug_name
    src = source or "Mecp2-null cortex RNA-seq"

    chain: list[EvidenceLink] = [
        EvidenceLink(
            kind="signature_reversal",
            description=(
                f"{drug_name}'s L1000 perturbation signature reverses the Rett "
                f"expression signature (z-up {z_up:.2f}, z-down {z_down:.2f})"
                if z_up is not None and z_down is not None
                else f"{drug_name}'s L1000 signature reverses the Rett expression signature"
            ),
            metadata={
                "source": "SigCom LINCS (L1000)",
                "perturbagen": str(pert_name),
                "signatures_supporting": n_signatures,
            },
        ),
        EvidenceLink(
            kind="signature_provenance",
            description=(
                f"Reversal scored against the {n_signature_genes}-gene Rett cortex "
                f"signature derived from {src} (Mecp2-null vs wild-type)"
            ),
            metadata={"source": src, "signature_genes": n_signature_genes},
        ),
    ]

    if row.get("is_approved"):
        year = row.get("first_approval_year")
        chain.append(
            EvidenceLink(
                kind="approval_status",
                description=(
                    f"{drug_name} is an approved drug"
                    + (f" (first approval {year})" if year else "")
                    + " — an off-patent repurposing candidate"
                ),
                metadata={"source": "ChEMBL", "is_approved": 1},
            )
        )

    return chain


def _as_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
