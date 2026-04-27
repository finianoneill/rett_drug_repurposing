"""Typed query functions over the DuckDB store.

Phase 1 surfaces just the inserts/upserts used by `build_local_store.py` and
the lookups the `target_based` strategy needs (commit 3 will widen this).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import duckdb

from rett_repurposing.exceptions import StoreError


def upsert_disease(
    conn: duckdb.DuckDBPyConnection,
    *,
    efo_id: str,
    name: str,
    fetched_at: datetime,
) -> None:
    """Insert or replace a disease row."""
    try:
        conn.execute(
            "INSERT OR REPLACE INTO diseases (efo_id, name, fetched_at) VALUES (?, ?, ?)",
            [efo_id, name, fetched_at],
        )
    except duckdb.Error as exc:
        raise StoreError(f"upsert_disease failed: {exc}") from exc


def upsert_disease_target(
    conn: duckdb.DuckDBPyConnection,
    *,
    efo_id: str,
    target_ensembl_id: str,
    target_symbol: str | None,
    target_name: str | None,
    biotype: str | None,
    overall_association_score: float,
    datatype_scores: dict[str, float],
) -> None:
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO disease_targets
                (efo_id, target_ensembl_id, target_symbol, target_name, biotype,
                 overall_association_score, datatype_scores)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                efo_id,
                target_ensembl_id,
                target_symbol,
                target_name,
                biotype,
                overall_association_score,
                json.dumps(datatype_scores),
            ],
        )
    except duckdb.Error as exc:
        raise StoreError(f"upsert_disease_target failed: {exc}") from exc


def upsert_drug(
    conn: duckdb.DuckDBPyConnection,
    *,
    chembl_id: str,
    name: str,
    drug_type: str | None,
    max_phase: float | None,
    is_approved: bool,
    first_approval_year: int | None,
    withdrawn_flag: bool | None,
    trade_names: list[str],
    synonyms: list[str],
    canonical_smiles: str | None,
    atc_classifications: list[str],
) -> None:
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO drugs
                (chembl_id, name, drug_type, max_phase, is_approved,
                 first_approval_year, withdrawn_flag, trade_names, synonyms,
                 canonical_smiles, atc_classifications)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                chembl_id,
                name,
                drug_type,
                max_phase,
                is_approved,
                first_approval_year,
                withdrawn_flag,
                json.dumps(trade_names),
                json.dumps(synonyms),
                canonical_smiles,
                json.dumps(atc_classifications),
            ],
        )
    except duckdb.Error as exc:
        raise StoreError(f"upsert_drug failed: {exc}") from exc


def upsert_drug_target_disease(
    conn: duckdb.DuckDBPyConnection,
    *,
    chembl_id: str,
    target_ensembl_id: str,
    efo_id: str,
    phase: float | None,
    status: str | None,
    mechanism_of_action: str | None,
    ct_ids: list[str],
) -> None:
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO drug_target_disease
                (chembl_id, target_ensembl_id, efo_id, phase, status,
                 mechanism_of_action, ct_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                chembl_id,
                target_ensembl_id,
                efo_id,
                phase,
                status,
                mechanism_of_action,
                json.dumps(ct_ids),
            ],
        )
    except duckdb.Error as exc:
        raise StoreError(f"upsert_drug_target_disease failed: {exc}") from exc


def count_rows(conn: duckdb.DuckDBPyConnection, table: str) -> int:
    """Count rows in a table. Used by health checks and tests."""
    try:
        result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    except duckdb.Error as exc:
        raise StoreError(f"count on {table} failed: {exc}") from exc
    if result is None:
        return 0
    return int(result[0])


def fetch_approved_drugs_for_disease(
    conn: duckdb.DuckDBPyConnection,
    efo_id: str,
) -> list[dict[str, Any]]:
    """Return all rows of `approved_drugs_for_disease` for a given disease.

    Datatype-score JSON columns are decoded to dicts; ct_ids JSON to a list.
    """
    try:
        rows = conn.execute(
            "SELECT * FROM approved_drugs_for_disease WHERE efo_id = ?",
            [efo_id],
        ).fetchall()
        columns = [d[0] for d in conn.description or []]
    except duckdb.Error as exc:
        raise StoreError(f"fetch_approved_drugs_for_disease failed: {exc}") from exc

    return [_row_to_dict(columns, row) for row in rows]


def _row_to_dict(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    out: dict[str, Any] = dict(zip(columns, row, strict=True))
    for json_col in ("datatype_scores", "ct_ids"):
        if json_col in out and isinstance(out[json_col], str):
            try:
                out[json_col] = json.loads(out[json_col])
            except json.JSONDecodeError:
                out[json_col] = None
    return out
