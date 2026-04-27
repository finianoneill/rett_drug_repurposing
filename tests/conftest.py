"""Shared pytest fixtures."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

from rett_repurposing.store.connection import init_schema

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def memory_db() -> Iterator[duckdb.DuckDBPyConnection]:
    """In-memory DuckDB with the project schema applied."""
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def opentargets_fixtures() -> dict[str, Any]:
    """Recorded Open Targets responses for Rett syndrome (trimmed)."""
    return {
        "disease_search": json.loads(
            (FIXTURES / "opentargets" / "disease_search.json").read_text()
        ),
        "disease_targets": json.loads(
            (FIXTURES / "opentargets" / "disease_targets.json").read_text()
        ),
        "drug_candidates": json.loads(
            (FIXTURES / "opentargets" / "drug_candidates.json").read_text()
        ),
    }


@pytest.fixture
def chembl_fixture() -> dict[str, Any]:
    """Recorded ChEMBL molecules.json (trimmed)."""
    return json.loads((FIXTURES / "chembl" / "molecules.json").read_text())  # type: ignore[no-any-return]
