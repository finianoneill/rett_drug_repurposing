"""Context-managed DuckDB connection helpers.

DuckDB is single-writer: only one process should hold a write handle at a time
(see IMPLEMENTATION_BRIEF.md §5b). The backend opens read-only by default;
fetchers and `build_local_store.py` are the only writers.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from rett_repurposing.exceptions import StoreError

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@contextmanager
def get_connection(
    path: str | Path,
    *,
    read_only: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open a DuckDB connection, ensuring it is closed on exit.

    Args:
        path: filesystem path to the DuckDB file. Use `:memory:` for tests.
        read_only: open the file read-only (multiple readers can coexist).

    Yields:
        An open DuckDB connection.

    Raises:
        StoreError: if the file cannot be opened.
    """
    try:
        conn = duckdb.connect(database=str(path), read_only=read_only)
    except duckdb.Error as exc:
        raise StoreError(f"failed to open DuckDB at {path}: {exc}") from exc

    try:
        yield conn
    finally:
        conn.close()


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply the schema DDL to a connection. Idempotent.

    Reads schema.sql co-located with this module so the embedded DDL is the
    single source of truth.
    """
    try:
        conn.execute(SCHEMA_PATH.read_text())
    except duckdb.Error as exc:
        raise StoreError(f"failed to initialise schema: {exc}") from exc
