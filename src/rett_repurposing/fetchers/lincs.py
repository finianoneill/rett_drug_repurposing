"""SigCom LINCS client — Phase 2 signature reversal.

SigCom LINCS (Ma'ayan Lab) exposes a million L1000 signatures behind a free,
key-less REST API. Given an up/down disease gene signature, we ask which
chemical perturbagens *reverse* it. Three calls (see IMPLEMENTATION notes):

1. metadata-api ``/entities/find``     — gene symbols → entity UUIDs.
2. data-api ``/enrich/ranktwosided``   — up/down UUIDs → ranked signatures with
   two-sided z-scores. Reversers have negative z in both directions.
3. metadata-api ``/signatures/find``   — signature UUIDs → perturbagen metadata
   (drug name, PubChem id, cell line, dose).

The bare ``ldp3.cloud`` API host does not resolve publicly; the working base is
the ``maayanlab.cloud/sigcom-lincs`` reverse proxy (see ``Settings``).

Fetchers return raw JSON. Aggregation to one candidate per drug happens in
``scripts/build_local_store.py``, consistent with the other fetchers.
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
from rett_repurposing.exceptions import LincsError

log = structlog.get_logger(__name__)


# Batch size for signature-metadata resolution (query-body list, not URL).
SIGNATURE_BATCH_SIZE = 200


class SigComLincsClient:
    """Async client for the SigCom LINCS metadata + data APIs."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> SigComLincsClient:
        if self._client is None:
            # The data-api enrich endpoint answers POSTs with a 307 redirect;
            # follow_redirects lets httpx replay the POST to the canonical URL.
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(90.0), follow_redirects=True)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def _base(self) -> str:
        return self._settings.sigcom_lincs_base_url.rstrip("/")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, LincsError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        if self._client is None:
            raise LincsError("client used outside `async with` context")

        url = f"{self._base}/{path.lstrip('/')}"
        start = time.perf_counter()
        try:
            response = await self._client.post(url, json=body)
        except httpx.HTTPError as exc:
            raise LincsError(f"POST {path}: HTTP error: {exc}") from exc
        duration_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code >= 400:
            raise LincsError(f"POST {path}: HTTP {response.status_code}: {response.text[:200]}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise LincsError(f"POST {path}: invalid JSON: {exc}") from exc

        log.info(
            "lincs.fetch",
            path=path,
            duration_ms=duration_ms,
            response_bytes=len(response.content),
        )
        return payload

    async def resolve_entities(self, symbols: list[str]) -> dict[str, str]:
        """Map gene symbols to SigCom entity UUIDs. Unknown symbols are dropped."""
        if not symbols:
            return {}
        payload = await self._post(
            "metadata-api/entities/find",
            {
                "filter": {
                    "where": {"meta.symbol": {"inq": symbols}},
                    "fields": ["id", "meta.symbol"],
                }
            },
        )
        if not isinstance(payload, list):
            raise LincsError("entities/find: expected a list response")
        resolved: dict[str, str] = {}
        for row in payload:
            symbol = row.get("meta", {}).get("symbol")
            uuid = row.get("id")
            if isinstance(symbol, str) and isinstance(uuid, str):
                resolved[symbol] = uuid
        return resolved

    async def enrich_ranktwosided(
        self,
        up_uuids: list[str],
        down_uuids: list[str],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Run the two-sided enrichment and return the raw ``results`` rows.

        The API returns both mimickers and reversers; callers filter by ``type``.
        """
        payload = await self._post(
            "data-api/api/v1/enrich/ranktwosided",
            {
                "up_entities": up_uuids,
                "down_entities": down_uuids,
                "limit": limit,
                "database": self._settings.lincs_database,
            },
        )
        if not isinstance(payload, dict):
            raise LincsError("enrich/ranktwosided: expected an object response")
        results = payload.get("results")
        if not isinstance(results, list):
            raise LincsError("enrich/ranktwosided: missing 'results' list")
        return results

    async def resolve_signatures(self, sig_uuids: list[str]) -> dict[str, dict[str, Any]]:
        """Map signature UUIDs to their perturbagen metadata (batched)."""
        meta_by_uuid: dict[str, dict[str, Any]] = {}
        for start in range(0, len(sig_uuids), SIGNATURE_BATCH_SIZE):
            batch = sig_uuids[start : start + SIGNATURE_BATCH_SIZE]
            payload = await self._post(
                "metadata-api/signatures/find",
                {"filter": {"where": {"id": {"inq": batch}}}},
            )
            if not isinstance(payload, list):
                raise LincsError("signatures/find: expected a list response")
            for row in payload:
                uuid = row.get("id")
                meta = row.get("meta")
                if isinstance(uuid, str) and isinstance(meta, dict):
                    meta_by_uuid[uuid] = meta
        return meta_by_uuid

    async def find_reversers(
        self,
        up_symbols: list[str],
        down_symbols: list[str],
        *,
        limit: int = 200,
    ) -> dict[str, Any]:
        """End-to-end: resolve genes, enrich, keep reversers, attach metadata.

        Returns a raw JSON-serialisable blob for persistence; ``reversers`` is a
        list of ``{uuid, z_up, z_down, z_sum, p_up, p_down, fdr_up, fdr_down,
        pert_name, pubchem_id, pert_type, cell_line, pert_dose, pert_time}``.
        """
        resolved_up = await self.resolve_entities(up_symbols)
        resolved_down = await self.resolve_entities(down_symbols)
        unresolved = sorted(
            (set(up_symbols) | set(down_symbols)) - set(resolved_up) - set(resolved_down)
        )
        if not resolved_up and not resolved_down:
            raise LincsError("no input gene symbols resolved to LINCS entities")

        rows = await self.enrich_ranktwosided(
            list(resolved_up.values()),
            list(resolved_down.values()),
            limit=limit,
        )
        reverser_rows = [r for r in rows if r.get("type") == "reversers"]
        log.info(
            "lincs.reversers",
            resolved_up=len(resolved_up),
            resolved_down=len(resolved_down),
            unresolved=len(unresolved),
            reverser_rows=len(reverser_rows),
        )

        sig_meta = await self.resolve_signatures([r["uuid"] for r in reverser_rows])

        reversers: list[dict[str, Any]] = []
        for r in reverser_rows:
            meta = sig_meta.get(r["uuid"], {})
            reversers.append(
                {
                    "uuid": r["uuid"],
                    "z_up": r.get("z-up"),
                    "z_down": r.get("z-down"),
                    "z_sum": r.get("z-sum"),
                    "p_up": r.get("p-up"),
                    "p_down": r.get("p-down"),
                    "fdr_up": r.get("fdr-up"),
                    "fdr_down": r.get("fdr-down"),
                    "pert_name": meta.get("pert_name"),
                    "pubchem_id": meta.get("pubchem_id"),
                    "pert_type": meta.get("pert_type"),
                    "cell_line": meta.get("cell_line"),
                    "pert_dose": meta.get("pert_dose"),
                    "pert_time": meta.get("pert_time"),
                }
            )

        return {
            "database": self._settings.lincs_database,
            "resolved_up": resolved_up,
            "resolved_down": resolved_down,
            "unresolved_symbols": unresolved,
            "reversers": reversers,
        }
