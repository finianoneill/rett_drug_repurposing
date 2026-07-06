"""GEO counts fetcher — Phase 2 disease signature.

Downloads a gzipped genes-by-samples counts matrix from NCBI GEO. The default
series (``GSE300534``, Mecp2-null mouse cortex) ships a self-describing
supplementary counts file: six metadata header rows (Brain Area, Sex, Genotype,
Injection Status, ...) followed by ``Ensembl ID`` / ``Gene ID`` (mouse symbol)
and per-sample integer counts.

The fetcher only downloads and decompresses. Differential expression and the
up/down signature are derived in ``rett_repurposing.signature``.
"""

from __future__ import annotations

import gzip
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
from rett_repurposing.exceptions import GEOError

log = structlog.get_logger(__name__)


class GeoClient:
    """Async client that downloads GEO supplementary counts matrices."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> GeoClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0), follow_redirects=True)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, GEOError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def fetch_counts(self, url: str | None = None) -> str:
        """Download the gzipped counts matrix and return the decompressed TSV text."""
        if self._client is None:
            raise GEOError("client used outside `async with` context")

        target = url or self._settings.geo_counts_url
        start = time.perf_counter()
        try:
            response = await self._client.get(target)
        except httpx.HTTPError as exc:
            raise GEOError(f"GET {target}: HTTP error: {exc}") from exc

        if response.status_code >= 400:
            raise GEOError(f"GET {target}: HTTP {response.status_code}")

        try:
            text = gzip.decompress(response.content).decode("utf-8")
        except (OSError, EOFError, UnicodeDecodeError) as exc:
            raise GEOError(f"GET {target}: could not gunzip/decode payload: {exc}") from exc

        duration_ms = int((time.perf_counter() - start) * 1000)
        log.info(
            "geo.fetch",
            url=target,
            duration_ms=duration_ms,
            compressed_bytes=len(response.content),
            decompressed_bytes=len(text),
        )
        return text
