"""DuckDB schema and basic upsert behavior."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from rett_repurposing.store.queries import (
    count_rows,
    fetch_approved_drugs_for_disease,
    fetch_disease_signature,
    fetch_signature_reversal_candidates,
    upsert_disease,
    upsert_disease_signature,
    upsert_disease_target,
    upsert_drug,
    upsert_drug_signature_reversal,
    upsert_drug_target_disease,
)


def test_schema_creates_expected_tables(memory_db):
    rows = memory_db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {
        "diseases",
        "disease_targets",
        "drugs",
        "drug_target_disease",
        "disease_signature",
        "drug_signature_reversal",
    } <= names


def test_view_approved_drugs_exists(memory_db):
    rows = memory_db.execute(
        "SELECT view_name FROM duckdb_views() WHERE schema_name = 'main'"
    ).fetchall()
    views = {r[0] for r in rows}
    assert "approved_drugs_for_disease" in views
    assert "signature_reversal_for_disease" in views


def test_upsert_idempotency(memory_db):
    upsert_disease(
        memory_db,
        efo_id="MONDO_0010726",
        name="Rett syndrome",
        fetched_at=datetime.now(tz=UTC),
    )
    upsert_disease(
        memory_db,
        efo_id="MONDO_0010726",
        name="Rett syndrome",
        fetched_at=datetime.now(tz=UTC),
    )
    assert count_rows(memory_db, "diseases") == 1


def test_approved_drugs_view_filters_unapproved(memory_db):
    upsert_disease(
        memory_db,
        efo_id="EFO1",
        name="Demo",
        fetched_at=datetime.now(tz=UTC),
    )
    upsert_disease_target(
        memory_db,
        efo_id="EFO1",
        target_ensembl_id="ENSG_T1",
        target_symbol="T1",
        target_name="Target One",
        biotype="protein_coding",
        overall_association_score=0.75,
        datatype_scores={"literature": 0.8},
    )
    upsert_drug(
        memory_db,
        chembl_id="CHEMBL_APPROVED",
        name="ApprovedDrug",
        drug_type="Small molecule",
        max_phase=4.0,
        is_approved=True,
        first_approval_year=2018,
        withdrawn_flag=False,
        trade_names=["Brand"],
        synonyms=["alias"],
        canonical_smiles="C",
        atc_classifications=["N01"],
    )
    upsert_drug(
        memory_db,
        chembl_id="CHEMBL_INVESTIGATIONAL",
        name="InvestigationalDrug",
        drug_type="Small molecule",
        max_phase=2.0,
        is_approved=False,
        first_approval_year=None,
        withdrawn_flag=False,
        trade_names=[],
        synonyms=[],
        canonical_smiles=None,
        atc_classifications=[],
    )
    upsert_drug_target_disease(
        memory_db,
        chembl_id="CHEMBL_APPROVED",
        target_ensembl_id="ENSG_T1",
        efo_id="EFO1",
        phase=4.0,
        status="Completed",
        mechanism_of_action="agonist",
        ct_ids=["NCT0001"],
    )
    upsert_drug_target_disease(
        memory_db,
        chembl_id="CHEMBL_INVESTIGATIONAL",
        target_ensembl_id="ENSG_T1",
        efo_id="EFO1",
        phase=2.0,
        status="Recruiting",
        mechanism_of_action="inhibitor",
        ct_ids=["NCT0002"],
    )

    rows = fetch_approved_drugs_for_disease(memory_db, "EFO1")
    assert len(rows) == 1
    row = rows[0]
    assert row["chembl_id"] == "CHEMBL_APPROVED"
    assert row["target_symbol"] == "T1"
    assert row["overall_association_score"] == 0.75
    assert row["mechanism_of_action"] == "agonist"
    assert row["ct_ids"] == ["NCT0001"]


def test_disease_target_datatype_scores_round_trip(memory_db):
    upsert_disease(
        memory_db,
        efo_id="EFO1",
        name="Demo",
        fetched_at=datetime.now(tz=UTC),
    )
    upsert_disease_target(
        memory_db,
        efo_id="EFO1",
        target_ensembl_id="ENSG_T1",
        target_symbol="T1",
        target_name="Target One",
        biotype="protein_coding",
        overall_association_score=0.6,
        datatype_scores={"genetic_association": 0.9, "literature": 0.5},
    )
    raw = memory_db.execute(
        "SELECT datatype_scores FROM disease_targets WHERE target_ensembl_id = 'ENSG_T1'"
    ).fetchone()
    assert raw is not None
    decoded = json.loads(raw[0])
    assert decoded == {"genetic_association": 0.9, "literature": 0.5}


def _seed_disease(conn) -> None:
    upsert_disease(conn, efo_id="EFO1", name="Demo", fetched_at=datetime.now(tz=UTC))


def test_disease_signature_round_trip(memory_db):
    _seed_disease(memory_db)
    upsert_disease_signature(
        memory_db, efo_id="EFO1", gene_symbol="IRAK1", direction="up", rank=1, source="GSE300534"
    )
    upsert_disease_signature(
        memory_db, efo_id="EFO1", gene_symbol="MECP2", direction="down", rank=1, source="GSE300534"
    )
    upsert_disease_signature(
        memory_db, efo_id="EFO1", gene_symbol="BDNF", direction="down", rank=2, source="GSE300534"
    )
    signature = fetch_disease_signature(memory_db, "EFO1")
    assert signature["up"] == ["IRAK1"]
    assert signature["down"] == ["MECP2", "BDNF"]  # ordered by rank


def test_signature_reversal_view_orders_and_filters(memory_db):
    _seed_disease(memory_db)
    # An approved reverser and a withdrawn one; the view excludes withdrawn.
    upsert_drug(
        memory_db,
        chembl_id="CHEMBL_VPA",
        name="VALPROIC ACID",
        drug_type="Small molecule",
        max_phase=4.0,
        is_approved=True,
        first_approval_year=1983,
        withdrawn_flag=False,
        trade_names=[],
        synonyms=[],
        canonical_smiles=None,
        atc_classifications=[],
    )
    upsert_drug(
        memory_db,
        chembl_id="CHEMBL_WD",
        name="WITHDRAWN",
        drug_type="Small molecule",
        max_phase=4.0,
        is_approved=True,
        first_approval_year=1990,
        withdrawn_flag=True,
        trade_names=[],
        synonyms=[],
        canonical_smiles=None,
        atc_classifications=[],
    )
    upsert_drug_signature_reversal(
        memory_db,
        efo_id="EFO1",
        chembl_id="CHEMBL_VPA",
        pert_name="valproic-acid",
        z_up=-4.0,
        z_down=-4.1,
        z_sum=-8.1,
        reversal_score=8.1,
        n_signatures=3,
    )
    upsert_drug_signature_reversal(
        memory_db,
        efo_id="EFO1",
        chembl_id="CHEMBL_WD",
        pert_name="withdrawn",
        z_up=-5.0,
        z_down=-5.0,
        z_sum=-10.0,
        reversal_score=10.0,
        n_signatures=1,
    )
    rows = fetch_signature_reversal_candidates(memory_db, "EFO1")
    assert [r["chembl_id"] for r in rows] == ["CHEMBL_VPA"]  # withdrawn filtered
    assert rows[0]["n_signatures"] == 3
