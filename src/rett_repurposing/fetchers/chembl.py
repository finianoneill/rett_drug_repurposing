"""ChEMBL REST client.

For Phase 1 ChEMBL's role is enrichment only — see IMPLEMENTATION_BRIEF.md §6.2.
Fetchers return raw JSON; parsing happens in `build_local_store.py`.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from rett_repurposing.config import Settings, get_settings
from rett_repurposing.exceptions import ChEMBLError

log = structlog.get_logger(__name__)


# ChEMBL's URL line-length tolerance is generous in practice but we keep batches
# conservative — the molecule_chembl_id__in filter encodes IDs in the query string.
DEFAULT_BATCH_SIZE = 50


class ChEMBLClient:
    """Async client for the ChEMBL REST API."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> ChEMBLClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, ChEMBLError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._client is None:
            raise ChEMBLError("client used outside `async with` context")

        url = f"{self._settings.chembl_base_url.rstrip('/')}/{path.lstrip('/')}"
        start = time.perf_counter()
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ChEMBLError(f"GET {path}: HTTP error: {exc}") from exc
        duration_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code == 404:
            raise ChEMBLError(f"GET {path}: 404 not found")
        if response.status_code >= 400:
            raise ChEMBLError(f"GET {path}: HTTP {response.status_code}: {response.text[:200]}")

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ChEMBLError(f"GET {path}: invalid JSON: {exc}") from exc

        log.info(
            "chembl.fetch",
            path=path,
            params=params,
            duration_ms=duration_ms,
            response_bytes=len(response.content),
        )
        return payload

    async def fetch_molecule(self, chembl_id: str) -> dict[str, Any]:
        """Fetch a single molecule by ChEMBL ID. Returns raw JSON."""
        return await self._get(f"molecule/{chembl_id}.json")

    async def resolve_molecule_by_name(self, name: str) -> dict[str, Any] | None:
        """Look up a molecule by drug name (case-insensitive).

        Used by the Phase 2 signature-reversal fetcher to map a LINCS
        perturbagen name to a ChEMBL molecule. Tries the preferred name first,
        then synonyms. Returns the raw molecule JSON, or ``None`` if unmatched
        (e.g. research compounds with only a Broad ``BRD-…`` code).
        """
        normalized = name.replace("-", " ").strip().upper()
        if not normalized:
            return None
        for field in ("pref_name__iexact", "molecule_synonyms__molecule_synonym__iexact"):
            payload = await self._get("molecule.json", params={field: normalized, "limit": 1})
            molecules = payload.get("molecules", [])
            if molecules:
                molecule: dict[str, Any] = molecules[0]
                return molecule
        return None

    async def fetch_molecules_batch(
        self,
        chembl_ids: list[str],
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> list[dict[str, Any]]:
        """Fetch many molecules using `molecule_chembl_id__in`.

        Splits requests into batches to keep URL length sane. Returns the
        flat list of molecule objects across all batches.
        """
        all_molecules: list[dict[str, Any]] = []
        for start in range(0, len(chembl_ids), batch_size):
            batch = chembl_ids[start : start + batch_size]
            payload = await self._get(
                "molecule.json",
                params={
                    "molecule_chembl_id__in": ",".join(batch),
                    "limit": batch_size,
                },
            )
            all_molecules.extend(payload.get("molecules", []))
        return all_molecules
