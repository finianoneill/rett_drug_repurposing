"""End-to-end test of the store builder against fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from rett_repurposing.store.build import build, stage_to_phase
from rett_repurposing.store.connection import get_connection
from rett_repurposing.store.queries import count_rows, fetch_approved_drugs_for_disease


def _stage_data(tmp_path: Path, opentargets_fixtures, chembl_fixture) -> tuple[Path, Path]:
    ot_dir = tmp_path / "opentargets"
    chembl_dir = tmp_path / "chembl"
    ot_dir.mkdir()
    chembl_dir.mkdir()
    (ot_dir / "disease_targets.json").write_text(
        json.dumps(opentargets_fixtures["disease_targets"])
    )
    (ot_dir / "drug_candidates.json").write_text(
        json.dumps(opentargets_fixtures["drug_candidates"])
    )
    (chembl_dir / "molecules.json").write_text(json.dumps(chembl_fixture))
    return ot_dir, chembl_dir


def test_build_populates_tables(tmp_path: Path, opentargets_fixtures, chembl_fixture):
    ot_dir, chembl_dir = _stage_data(tmp_path, opentargets_fixtures, chembl_fixture)
    duckdb_path = tmp_path / "store.duckdb"

    build(ot_dir, chembl_dir, duckdb_path)

    with get_connection(duckdb_path, read_only=True) as conn:
        assert count_rows(conn, "diseases") == 1
        assert count_rows(conn, "disease_targets") == 3
        assert count_rows(conn, "drugs") == 2
        assert count_rows(conn, "drug_target_disease") == 2

        approved = fetch_approved_drugs_for_disease(conn, "MONDO_0010726")
        # Trofinetide → IGF1 association exists, Fingolimod → BDNF association exists,
        # both drugs are approved per ChEMBL max_phase=4.0.
        assert len(approved) == 2
        chembl_ids = {row["chembl_id"] for row in approved}
        assert {"CHEMBL_TROF", "CHEMBL314854"} == chembl_ids


def test_build_is_idempotent(tmp_path: Path, opentargets_fixtures, chembl_fixture):
    ot_dir, chembl_dir = _stage_data(tmp_path, opentargets_fixtures, chembl_fixture)
    duckdb_path = tmp_path / "store.duckdb"

    build(ot_dir, chembl_dir, duckdb_path)
    build(ot_dir, chembl_dir, duckdb_path)

    with get_connection(duckdb_path, read_only=True) as conn:
        assert count_rows(conn, "drugs") == 2
        assert count_rows(conn, "drug_target_disease") == 2


def test_stage_to_phase_mapping():
    assert stage_to_phase("APPROVAL") == 4.0
    assert stage_to_phase("PHASE_3") == 3.0
    assert stage_to_phase("PHASE_1_2") == 1.5
    assert stage_to_phase("PRECLINICAL") == 0.0
    assert stage_to_phase(None) is None
    assert stage_to_phase("UNKNOWN_STAGE_XYZ") is None
