"""Fetcher parsing tests using `httpx.MockTransport` and recorded fixtures.

These do not hit live APIs. The fetcher contract is "return raw JSON" — most
of the interesting transformation logic is exercised in `test_build_store.py`.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from rett_repurposing.exceptions import ChEMBLError, OpenTargetsError
from rett_repurposing.fetchers.chembl import ChEMBLClient
from rett_repurposing.fetchers.opentargets import OpenTargetsClient


def _ot_handler(payload: dict[str, Any]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # echo back the requested operation so tests can inspect it
        return httpx.Response(200, json={"data": payload, "_received": body})

    return handler


@pytest.mark.asyncio
async def test_search_disease_returns_raw_data(opentargets_fixtures):
    transport = httpx.MockTransport(_ot_handler(opentargets_fixtures["disease_search"]))
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenTargetsClient(client=http)
        data = await client.search_disease("Rett syndrome")
    assert data["search"]["hits"][0]["id"] == "MONDO_0010726"


@pytest.mark.asyncio
async def test_resolve_disease_id_picks_top_hit(opentargets_fixtures):
    transport = httpx.MockTransport(_ot_handler(opentargets_fixtures["disease_search"]))
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenTargetsClient(client=http)
        efo_id, name = await client.resolve_disease_id("Rett syndrome")
    assert efo_id == "MONDO_0010726"
    assert name == "Rett syndrome"


@pytest.mark.asyncio
async def test_resolve_disease_id_raises_on_no_hits():
    transport = httpx.MockTransport(_ot_handler({"search": {"hits": []}}))
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenTargetsClient(client=http)
        with pytest.raises(OpenTargetsError):
            await client.resolve_disease_id("nonsense")


@pytest.mark.asyncio
async def test_graphql_errors_become_typed_exception():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad query"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenTargetsClient(client=http)
        with pytest.raises(OpenTargetsError, match="GraphQL errors"):
            await client.search_disease("x")


@pytest.mark.asyncio
async def test_chembl_fetch_molecule(chembl_fixture):
    target_chembl = chembl_fixture["molecules"][0]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/molecule/CHEMBL_TROF.json")
        return httpx.Response(200, json=target_chembl)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = ChEMBLClient(client=http)
        data = await client.fetch_molecule("CHEMBL_TROF")
    assert data["molecule_chembl_id"] == "CHEMBL_TROF"


@pytest.mark.asyncio
async def test_chembl_batch_splits_request(chembl_fixture):
    requested_ids: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ids = request.url.params.get("molecule_chembl_id__in", "").split(",")
        requested_ids.extend(ids)
        molecules = [m for m in chembl_fixture["molecules"] if m["molecule_chembl_id"] in ids]
        return httpx.Response(200, json={"molecules": molecules})

    transport = httpx.MockTransport(handler)
    ids = ["CHEMBL_TROF", "CHEMBL314854"]
    async with httpx.AsyncClient(transport=transport) as http:
        client = ChEMBLClient(client=http)
        molecules = await client.fetch_molecules_batch(ids, batch_size=1)
    assert len(molecules) == 2
    assert sorted(requested_ids) == sorted(ids)


@pytest.mark.asyncio
async def test_chembl_404_raises():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = ChEMBLClient(client=http)
        with pytest.raises(ChEMBLError):
            await client.fetch_molecule("CHEMBL_DOESNOTEXIST")
