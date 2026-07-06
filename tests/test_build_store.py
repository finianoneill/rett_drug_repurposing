"""End-to-end test of the store builder against fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from rett_repurposing.store.build import build, stage_to_phase
from rett_repurposing.store.connection import get_connection
from rett_repurposing.store.queries import (
    count_rows,
    fetch_approved_drugs_for_disease,
    fetch_disease_signature,
    fetch_signature_reversal_candidates,
)


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


def _stage_phase2(tmp_path: Path) -> tuple[Path, Path]:
    sig_dir = tmp_path / "signature"
    lincs_dir = tmp_path / "lincs"
    sig_dir.mkdir()
    lincs_dir.mkdir()
    (sig_dir / "rett_signature.json").write_text(
        json.dumps(
            {
                "__meta__": {"source": "GSE300534"},
                "up_genes": ["IRAK1"],
                "down_genes": ["MECP2", "BDNF"],
            }
        )
    )
    (lincs_dir / "reversers.json").write_text(
        json.dumps(
            {
                "reversers": [
                    # Two signatures for the same drug -> aggregated, strongest kept.
                    {
                        "pert_name": "valproic-acid",
                        "chembl_id": "CHEMBL_VPA",
                        "z_up": -4.0,
                        "z_down": -4.1,
                        "z_sum": -8.1,
                    },
                    {
                        "pert_name": "valproic-acid",
                        "chembl_id": "CHEMBL_VPA",
                        "z_up": -2.0,
                        "z_down": -2.0,
                        "z_sum": -4.0,
                    },
                    # A reverser already present via Open Targets (must not clobber).
                    {
                        "pert_name": "fingolimod",
                        "chembl_id": "CHEMBL314854",
                        "z_up": -3.0,
                        "z_down": -3.0,
                        "z_sum": -6.0,
                    },
                ],
                "molecules": [
                    {
                        "molecule_chembl_id": "CHEMBL_VPA",
                        "pref_name": "VALPROIC ACID",
                        "max_phase": "4.0",
                        "molecule_type": "Small molecule",
                    },
                    {
                        "molecule_chembl_id": "CHEMBL314854",
                        "pref_name": "CLOBBERED",
                        "max_phase": "4.0",
                    },
                ],
            }
        )
    )
    return sig_dir, lincs_dir


def test_build_ingests_phase2_signature_and_reversers(
    tmp_path: Path, opentargets_fixtures, chembl_fixture
):
    ot_dir, chembl_dir = _stage_data(tmp_path, opentargets_fixtures, chembl_fixture)
    sig_dir, lincs_dir = _stage_phase2(tmp_path)
    duckdb_path = tmp_path / "store.duckdb"

    build(ot_dir, chembl_dir, duckdb_path, signature_dir=sig_dir, lincs_dir=lincs_dir)

    with get_connection(duckdb_path, read_only=True) as conn:
        signature = fetch_disease_signature(conn, "MONDO_0010726")
        assert signature["up"] == ["IRAK1"]
        assert signature["down"] == ["MECP2", "BDNF"]

        reversals = fetch_signature_reversal_candidates(conn, "MONDO_0010726")
        by_id = {r["chembl_id"]: r for r in reversals}
        # VPA aggregated to the strongest reversing signature.
        assert by_id["CHEMBL_VPA"]["z_sum"] == -8.1
        assert by_id["CHEMBL_VPA"]["n_signatures"] == 2
        # The Open Targets drug row was not clobbered by the LINCS molecule.
        name = conn.execute("SELECT name FROM drugs WHERE chembl_id = 'CHEMBL314854'").fetchone()[0]
        assert name != "CLOBBERED"


def test_build_without_phase2_leaves_signature_empty(
    tmp_path: Path, opentargets_fixtures, chembl_fixture
):
    ot_dir, chembl_dir = _stage_data(tmp_path, opentargets_fixtures, chembl_fixture)
    duckdb_path = tmp_path / "store.duckdb"

    build(ot_dir, chembl_dir, duckdb_path)  # no Phase 2 dirs

    with get_connection(duckdb_path, read_only=True) as conn:
        assert count_rows(conn, "disease_signature") == 0
        assert count_rows(conn, "drug_signature_reversal") == 0


def test_stage_to_phase_mapping():
    assert stage_to_phase("APPROVAL") == 4.0
    assert stage_to_phase("PHASE_3") == 3.0
    assert stage_to_phase("PHASE_1_2") == 1.5
    assert stage_to_phase("PRECLINICAL") == 0.0
    assert stage_to_phase(None) is None
    assert stage_to_phase("UNKNOWN_STAGE_XYZ") is None
