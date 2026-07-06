"""Phase 1 oracle validation — IMPLEMENTATION_BRIEF.md §14.

Runs the full target-based pipeline against the real `data/rett_repurposing.duckdb`
and asserts oracle coverage across the four canonical Rett pathway classes.

Skipped when the DuckDB file is missing (e.g., on fresh checkouts and in CI).
Skipped via the `validation` marker so CI runs `pytest -m "not validation"`
without needing the populated store.

Per §15.3: Phase 1 ships when this test passes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from rett_repurposing.models import Disease
from rett_repurposing.strategies.signature_reversal import SignatureReversalStrategy
from rett_repurposing.strategies.target_based import TargetBasedStrategy

DUCKDB_PATH = Path("data/rett_repurposing.duckdb")
ORACLE_PATH = Path(__file__).parent / "fixtures" / "rett_oracle.json"

# Why ≥3 not ≥4: the BDNF / TrkB pathway has zero FDA-approved drugs in Open
# Targets' approved-drugs graph for Rett at this time. Mecasermin (IGF-1),
# Ketamine/Esketamine/Dextromethorphan (NMDA), and Dextromethorphan (sigma-1)
# are the three pathways with current oracle coverage. See rett_oracle.json
# notes for details. If a BDNF/TrkB-pathway drug becomes approved this should
# tighten to ≥4.
MIN_COVERED_PATHWAYS = 3


@pytest.mark.validation
@pytest.mark.skipif(
    not DUCKDB_PATH.exists() or DUCKDB_PATH.stat().st_size == 0,
    reason="data/rett_repurposing.duckdb is empty — run `make fetch` first.",
)
async def test_oracle_coverage_in_top_20() -> None:
    oracle = json.loads(ORACLE_PATH.read_text())
    disease = Disease(**oracle["disease"])

    conn = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        strategy = TargetBasedStrategy(conn, top_n=20)
        result = await strategy.run(disease)
    finally:
        conn.close()

    top_chembl_ids = {c.drug.chembl_id for c in result.candidates}
    coverage = _coverage_report(oracle["pathways"], top_chembl_ids)

    print("\n=== Oracle coverage report ===")
    for pathway, info in coverage.items():
        if info["expected"] is None:
            print(f"  {pathway:<30} n/a (no approved drug known)")
            continue
        status = "HIT " if info["hit"] else "MISS"
        names = ", ".join(info["found_names"]) if info["found_names"] else "—"
        print(f"  [{status}] {pathway:<28} {names}")

    covered = sum(1 for info in coverage.values() if info["hit"])
    assert covered >= MIN_COVERED_PATHWAYS, (
        f"Oracle coverage too low: {covered}/{len(coverage)} pathways found in top 20. "
        f"Coverage detail: {coverage}"
    )


# Neuroactive reverser anchors with Rett relevance. Vorinostat is a strong
# cross-check: it also surfaces in the target-based strategy (HDAC axis), so
# concordance across two independent methods is a good methodology signal.
# Valproic acid and topiramate are anticonvulsants used clinically in Rett.
SIGNATURE_ANCHORS = {
    "CHEMBL98": "vorinostat",
    "CHEMBL109": "valproic acid",
    "CHEMBL220492": "topiramate",
}
MIN_REVERSAL_CANDIDATES = 20


@pytest.mark.validation
@pytest.mark.skipif(
    not DUCKDB_PATH.exists() or DUCKDB_PATH.stat().st_size == 0,
    reason="data/rett_repurposing.duckdb is empty — run `make fetch` first.",
)
async def test_signature_reversal_surfaces_neuroactive_reversers() -> None:
    oracle = json.loads(ORACLE_PATH.read_text())
    disease = Disease(**oracle["disease"])

    conn = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        result = await SignatureReversalStrategy(conn, top_n=20).run(disease)
    finally:
        conn.close()

    assert len(result.candidates) >= MIN_REVERSAL_CANDIDATES, (
        f"signature reversal produced only {len(result.candidates)} candidates "
        "— expected the LINCS reversal store to be populated (run `make fetch`)."
    )
    # Scores are normalised to [0, 1] with the strongest reverser at 1.0.
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == pytest.approx(1.0)
    # Genuine reversers have a negative z-sum.
    assert all(c.score_components.get("z_sum", 0.0) <= 0 for c in result.candidates)

    top_ids = {c.drug.chembl_id for c in result.candidates}
    hits = {name for cid, name in SIGNATURE_ANCHORS.items() if cid in top_ids}
    print("\n=== Signature-reversal anchors in top 20 ===")
    for cid, name in SIGNATURE_ANCHORS.items():
        print(f"  [{'HIT ' if cid in top_ids else 'miss'}] {name} ({cid})")
    assert hits, (
        "No neuroactive reverser anchor found in the top 20. Expected at least one "
        f"of {sorted(SIGNATURE_ANCHORS.values())}."
    )


def _coverage_report(
    pathways: dict[str, Any],
    found_chembl_ids: set[str],
) -> dict[str, dict[str, Any]]:
    """For each pathway, report whether any oracle drug landed in `found_chembl_ids`."""
    report: dict[str, dict[str, Any]] = {}
    for pathway, spec in pathways.items():
        drugs: list[dict[str, str]] = spec.get("drugs") or []
        if not drugs:
            report[pathway] = {"expected": None, "hit": False, "found_names": []}
            continue
        expected = {d["chembl_id"] for d in drugs}
        hit_ids = expected & found_chembl_ids
        found_names = [d["name"] for d in drugs if d["chembl_id"] in hit_ids]
        report[pathway] = {
            "expected": sorted(expected),
            "hit": bool(hit_ids),
            "found_names": found_names,
        }
    return report
