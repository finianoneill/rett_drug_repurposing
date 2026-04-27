"""Open Targets Platform GraphQL client.

Fetchers return *raw* GraphQL `data` payloads — no Pydantic parsing here.
That happens in `scripts/build_local_store.py` so the fetcher's only contract
is "fetch and persist" and re-shaping logic stays in one place.

Schema drift note (verified 2026-04-26): Open Targets' `Disease.knownDrugs`
field has been replaced with `Disease.drugAndClinicalCandidates`, with rows
restructured from {drug, target, phase, status, mechanismOfAction, ctIds} to
{id, maxClinicalStage, drug, clinicalReports[]}. Targets are now reached
through `drug.mechanismsOfAction.rows[].targets[]`. The query below matches
the live schema.
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
from rett_repurposing.exceptions import OpenTargetsError

log = structlog.get_logger(__name__)


SEARCH_QUERY = """
query SearchDisease($queryString: String!) {
  search(queryString: $queryString, entityNames: ["disease"]) {
    hits {
      id
      name
      entity
    }
  }
}
""".strip()


DISEASE_TARGETS_QUERY = """
query DiseaseTargets($efoId: String!, $size: Int!) {
  disease(efoId: $efoId) {
    id
    name
    associatedTargets(page: { index: 0, size: $size }) {
      count
      rows {
        target {
          id
          approvedSymbol
          approvedName
          biotype
        }
        score
        datatypeScores {
          id
          score
        }
      }
    }
  }
}
""".strip()


# Open Targets renamed `knownDrugs` → `drugAndClinicalCandidates` and removed
# the size argument; it returns the full set in one call.
DRUG_CANDIDATES_QUERY = """
query DrugCandidates($efoId: String!) {
  disease(efoId: $efoId) {
    id
    name
    drugAndClinicalCandidates {
      count
      rows {
        id
        maxClinicalStage
        drug {
          id
          name
          drugType
          maximumClinicalStage
          tradeNames
          synonyms
          mechanismsOfAction {
            rows {
              mechanismOfAction
              targets {
                id
                approvedSymbol
              }
            }
          }
        }
        clinicalReports {
          id
          source
          clinicalStage
          trialPhase
          trialOverallStatus
          phaseFromSource
          url
          year
        }
      }
    }
  }
}
""".strip()


class OpenTargetsClient:
    """Async GraphQL client with retry/backoff."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> OpenTargetsClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, OpenTargetsError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _post(
        self,
        query: str,
        variables: dict[str, Any],
        *,
        operation: str,
    ) -> dict[str, Any]:
        if self._client is None:
            raise OpenTargetsError("client used outside `async with` context")

        start = time.perf_counter()
        try:
            response = await self._client.post(
                self._settings.opentargets_graphql_url,
                json={"query": query, "variables": variables},
            )
        except httpx.HTTPError as exc:
            raise OpenTargetsError(f"{operation}: HTTP error: {exc}") from exc
        duration_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code >= 500:
            # Tenacity should retry these.
            raise OpenTargetsError(
                f"{operation}: HTTP {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise OpenTargetsError(
                f"{operation}: HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenTargetsError(f"{operation}: invalid JSON response: {exc}") from exc

        if errors := payload.get("errors"):
            raise OpenTargetsError(f"{operation}: GraphQL errors: {errors}")

        data = payload.get("data")
        if data is None:
            raise OpenTargetsError(f"{operation}: missing 'data' in response")

        log.info(
            "opentargets.fetch",
            operation=operation,
            variables=variables,
            duration_ms=duration_ms,
            response_bytes=len(response.content),
        )
        return data  # type: ignore[no-any-return]

    async def search_disease(self, query_string: str) -> dict[str, Any]:
        """Run a `search` query over the disease entity index. Returns raw `data`."""
        return await self._post(
            SEARCH_QUERY,
            {"queryString": query_string},
            operation="search_disease",
        )

    async def fetch_disease_targets(
        self,
        efo_id: str,
        size: int = 100,
    ) -> dict[str, Any]:
        """Run the DiseaseTargets query. Returns raw `data` (top-level `disease`)."""
        return await self._post(
            DISEASE_TARGETS_QUERY,
            {"efoId": efo_id, "size": size},
            operation="fetch_disease_targets",
        )

    async def fetch_drug_candidates(self, efo_id: str) -> dict[str, Any]:
        """Run the drugAndClinicalCandidates query. Returns raw `data`."""
        return await self._post(
            DRUG_CANDIDATES_QUERY,
            {"efoId": efo_id},
            operation="fetch_drug_candidates",
        )

    async def resolve_disease_id(self, query_string: str) -> tuple[str, str]:
        """Look up the canonical disease ID for a free-text name.

        Returns the (id, name) of the highest-ranked hit and logs a warning
        if the top hit's name doesn't case-insensitively match the query.

        Raises:
            OpenTargetsError: if `search` returns no disease hits.
        """
        data = await self.search_disease(query_string)
        hits = data.get("search", {}).get("hits", [])
        disease_hits = [h for h in hits if h.get("entity") == "disease"]
        if not disease_hits:
            raise OpenTargetsError(f"no disease hit for query: {query_string!r}")

        top = disease_hits[0]
        if query_string.lower().strip() not in top.get("name", "").lower():
            log.warning(
                "opentargets.resolve_disease.fuzzy_match",
                query=query_string,
                resolved_id=top["id"],
                resolved_name=top["name"],
            )
        else:
            log.info(
                "opentargets.resolve_disease",
                query=query_string,
                resolved_id=top["id"],
                resolved_name=top["name"],
            )
        return top["id"], top["name"]
