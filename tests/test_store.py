"""DuckDB schema and basic upsert behavior."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from rett_repurposing.store.queries import (
    count_rows,
    fetch_approved_drugs_for_disease,
    upsert_disease,
    upsert_disease_target,
    upsert_drug,
    upsert_drug_target_disease,
)


def test_schema_creates_expected_tables(memory_db):
    rows = memory_db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"diseases", "disease_targets", "drugs", "drug_target_disease"} <= names


def test_view_approved_drugs_exists(memory_db):
    rows = memory_db.execute(
        "SELECT view_name FROM duckdb_views() WHERE schema_name = 'main'"
    ).fetchall()
    assert "approved_drugs_for_disease" in {r[0] for r in rows}


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
