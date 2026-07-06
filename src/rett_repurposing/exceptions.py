"""Typed exceptions. Modules should raise these rather than letting
`httpx.HTTPError`, `duckdb.Error`, etc. bubble up to callers.
"""

from __future__ import annotations


class RepurposingError(Exception):
    """Base class for all project-specific errors."""


class OpenTargetsError(RepurposingError):
    """Open Targets GraphQL API failure (HTTP, GraphQL errors, malformed payload)."""


class ChEMBLError(RepurposingError):
    """ChEMBL REST API failure (HTTP, malformed payload)."""


class GEOError(RepurposingError):
    """GEO download failure (HTTP, malformed/unexpected counts matrix)."""


class LincsError(RepurposingError):
    """SigCom LINCS API failure (HTTP, malformed payload, unknown gene symbols)."""


class StoreError(RepurposingError):
    """DuckDB store failure (schema, query, transaction)."""


class FetchError(RepurposingError):
    """Generic fetcher failure that doesn't fit OT/ChEMBL specifics."""
