"""Transform raw OT + ChEMBL JSON into a populated DuckDB store.

The actual entry point is `scripts/build_local_store.py`; this module holds
the importable logic so it can be unit-tested without a subprocess.

Idempotent: every write goes through `INSERT OR REPLACE` and is bracketed in
a single transaction. A failure rolls back the partial state.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import structlog

from rett_repurposing.exceptions import StoreError
from rett_repurposing.store.connection import get_connection, init_schema
from rett_repurposing.store.queries import (
    upsert_disease,
    upsert_disease_target,
    upsert_drug,
    upsert_drug_target_disease,
)

log = structlog.get_logger(__name__)


# OT renamed phases to a string ENUM. Map back to the numeric scale the brief
# specifies (DOUBLE in `drugs.max_phase` and `drug_target_disease.phase`).
# 0.5 / 1.5 / 2.5 are not standard "max phase" values but preserve ordering.
PHASE_MAP: dict[str, float | None] = {
    "APPROVAL": 4.0,
    "APPROVED": 4.0,
    "PHASE_4": 4.0,
    "PREAPPROVAL": 3.5,
    "PHASE_3": 3.0,
    "PHASE_2_3": 2.5,
    "PHASE_2": 2.0,
    "PHASE_1_2": 1.5,
    "PHASE_1": 1.0,
    "EARLY_PHASE_1": 0.5,
    "PRECLINICAL": 0.0,
    "NA": None,
    "": None,
}


def stage_to_phase(stage: str | None) -> float | None:
    """Convert an OT clinicalStage string to a numeric phase. Unknown → None."""
    if stage is None:
        return None
    if stage in PHASE_MAP:
        return PHASE_MAP[stage]
    log.warning("phase.unknown_stage", stage=stage)
    return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing file: {path}")
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def _index_chembl_molecules(chembl_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return a {chembl_id: molecule} index from a fetch_chembl payload."""
    molecules: list[dict[str, Any]] = chembl_payload.get("molecules", [])
    return {m["molecule_chembl_id"]: m for m in molecules if m.get("molecule_chembl_id")}


def _coerce_max_phase(raw: Any) -> float | None:
    """ChEMBL returns max_phase as a string like '4.0' (sometimes None)."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _coerce_year(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _atc_codes(molecule: dict[str, Any]) -> list[str]:
    """ChEMBL returns atc_classifications as either a list of strings or
    a list of dicts depending on endpoint version. Coerce to list[str]."""
    raw = molecule.get("atc_classifications") or []
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, str):
            out.append(entry)
        elif isinstance(entry, dict):
            code = entry.get("level5") or entry.get("code") or entry.get("atc_code")
            if isinstance(code, str):
                out.append(code)
    return out


def build(
    opentargets_dir: Path,
    chembl_dir: Path,
    duckdb_path: Path,
) -> None:
    """Read raw fetcher output, populate the DuckDB store transactionally."""
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    targets_payload = _load_json(opentargets_dir / "disease_targets.json")
    drugs_payload = _load_json(opentargets_dir / "drug_candidates.json")
    chembl_payload = _load_json(chembl_dir / "molecules.json")

    fetched_at = datetime.now(tz=UTC)
    chembl_index = _index_chembl_molecules(chembl_payload)
    log.info("build.inputs_loaded", chembl_molecule_count=len(chembl_index))

    disease = targets_payload.get("disease") or {}
    efo_id = disease.get("id")
    name = disease.get("name")
    if not efo_id or not name:
        raise StoreError("disease_targets.json missing disease.id or disease.name")

    with get_connection(duckdb_path) as conn:
        init_schema(conn)
        try:
            conn.execute("BEGIN TRANSACTION")
            upsert_disease(conn, efo_id=efo_id, name=name, fetched_at=fetched_at)
            target_count = _ingest_targets(conn, targets_payload)
            drug_count, link_count = _ingest_drug_candidates(
                conn,
                drugs_payload=drugs_payload,
                efo_id=efo_id,
                chembl_index=chembl_index,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    log.info(
        "build.done",
        duckdb_path=str(duckdb_path),
        disease_targets=target_count,
        drugs=drug_count,
        drug_target_disease_links=link_count,
    )


def _ingest_targets(
    conn: duckdb.DuckDBPyConnection,
    targets_payload: dict[str, Any],
) -> int:
    rows = targets_payload.get("disease", {}).get("associatedTargets", {}).get("rows", [])
    efo_id = targets_payload.get("disease", {}).get("id")
    if efo_id is None:
        raise StoreError("disease.id missing from targets payload")

    for row in rows:
        target = row.get("target") or {}
        ensembl_id = target.get("id")
        if not ensembl_id:
            continue
        datatype_scores = {
            entry["id"]: entry["score"]
            for entry in row.get("datatypeScores", [])
            if entry.get("id") is not None and entry.get("score") is not None
        }
        upsert_disease_target(
            conn,
            efo_id=efo_id,
            target_ensembl_id=ensembl_id,
            target_symbol=target.get("approvedSymbol"),
            target_name=target.get("approvedName"),
            biotype=target.get("biotype"),
            overall_association_score=float(row.get("score") or 0.0),
            datatype_scores=datatype_scores,
        )
    return len(rows)


def _ingest_drug_candidates(
    conn: duckdb.DuckDBPyConnection,
    *,
    drugs_payload: dict[str, Any],
    efo_id: str,
    chembl_index: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    rows = drugs_payload.get("disease", {}).get("drugAndClinicalCandidates", {}).get("rows", [])

    seen_drugs: set[str] = set()
    seen_links: set[tuple[str, str, str]] = set()
    drug_count = 0
    link_count = 0

    for row in rows:
        drug = row.get("drug") or {}
        chembl_id = drug.get("id")
        if not chembl_id:
            continue

        if chembl_id not in seen_drugs:
            _ingest_drug(conn, drug=drug, chembl=chembl_index.get(chembl_id))
            seen_drugs.add(chembl_id)
            drug_count += 1

        row_phase = stage_to_phase(row.get("maxClinicalStage"))
        clinical_reports = row.get("clinicalReports") or []
        ct_ids = [r["id"] for r in clinical_reports if r.get("id")]
        statuses = [
            r.get("trialOverallStatus") for r in clinical_reports if r.get("trialOverallStatus")
        ]
        status = statuses[0] if statuses else None

        mech_rows = (drug.get("mechanismsOfAction") or {}).get("rows") or []
        for mech in mech_rows:
            mechanism = mech.get("mechanismOfAction")
            for target in mech.get("targets") or []:
                target_id = target.get("id")
                if not target_id:
                    continue
                key = (chembl_id, target_id, efo_id)
                if key in seen_links:
                    continue
                upsert_drug_target_disease(
                    conn,
                    chembl_id=chembl_id,
                    target_ensembl_id=target_id,
                    efo_id=efo_id,
                    phase=row_phase,
                    status=status,
                    mechanism_of_action=mechanism,
                    ct_ids=ct_ids,
                )
                seen_links.add(key)
                link_count += 1

    return drug_count, link_count


def _ingest_drug(
    conn: duckdb.DuckDBPyConnection,
    *,
    drug: dict[str, Any],
    chembl: dict[str, Any] | None,
) -> None:
    chembl_id = drug["id"]
    chembl = chembl or {}

    structures = chembl.get("molecule_structures") or {}
    canonical_smiles = structures.get("canonical_smiles") if isinstance(structures, dict) else None

    chembl_max_phase = _coerce_max_phase(chembl.get("max_phase"))
    ot_stage_phase = stage_to_phase(drug.get("maximumClinicalStage"))
    # Prefer ChEMBL when present (canonical drug-development phase), fall back to OT.
    max_phase = chembl_max_phase if chembl_max_phase is not None else ot_stage_phase

    is_approved = (max_phase is not None and max_phase >= 4.0) or drug.get(
        "maximumClinicalStage"
    ) == "APPROVAL"

    withdrawn = chembl.get("withdrawn_flag")
    withdrawn_bool = bool(withdrawn) if withdrawn is not None else None

    name = drug.get("name") or chembl.get("pref_name") or chembl_id

    upsert_drug(
        conn,
        chembl_id=chembl_id,
        name=name,
        drug_type=drug.get("drugType") or chembl.get("molecule_type"),
        max_phase=max_phase,
        is_approved=is_approved,
        first_approval_year=_coerce_year(chembl.get("first_approval")),
        withdrawn_flag=withdrawn_bool,
        trade_names=list(drug.get("tradeNames") or []),
        synonyms=list(drug.get("synonyms") or []),
        canonical_smiles=canonical_smiles,
        atc_classifications=_atc_codes(chembl),
    )
