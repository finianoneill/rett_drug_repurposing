"""Fetcher parsing tests using `httpx.MockTransport` and recorded fixtures.

These do not hit live APIs. The fetcher contract is "return raw JSON" — most
of the interesting transformation logic is exercised in `test_build_store.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from rett_repurposing.exceptions import ChEMBLError, LincsError, OpenTargetsError
from rett_repurposing.fetchers.chembl import ChEMBLClient
from rett_repurposing.fetchers.lincs import SigComLincsClient
from rett_repurposing.fetchers.opentargets import OpenTargetsClient

FIXTURES = Path(__file__).parent / "fixtures"


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


@pytest.mark.asyncio
async def test_chembl_resolve_by_name_normalizes_and_falls_back():
    seen_filters: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if "pref_name__iexact" in params:
            seen_filters.append("pref_name")
            assert params["pref_name__iexact"] == "VALPROIC ACID"  # hyphen -> space, upper
            return httpx.Response(200, json={"molecules": []})  # miss -> triggers fallback
        seen_filters.append("synonym")
        return httpx.Response(200, json={"molecules": [{"molecule_chembl_id": "CHEMBL109"}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = ChEMBLClient(client=http)
        molecule = await client.resolve_molecule_by_name("valproic-acid")
    assert molecule is not None
    assert molecule["molecule_chembl_id"] == "CHEMBL109"
    assert seen_filters == ["pref_name", "synonym"]


@pytest.mark.asyncio
async def test_chembl_resolve_by_name_returns_none_when_unmatched():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"molecules": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = ChEMBLClient(client=http)
        assert await client.resolve_molecule_by_name("BRD-K12345678") is None


def _lincs_handler():
    """Route the three SigCom endpoints to their recorded fixtures."""
    entities = json.loads((FIXTURES / "lincs" / "entities_find.json").read_text())
    enrich = json.loads((FIXTURES / "lincs" / "enrich.json").read_text())
    signatures = json.loads((FIXTURES / "lincs" / "signatures_find.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/entities/find"):
            body = json.loads(request.content)
            wanted = set(body["filter"]["where"]["meta.symbol"]["inq"])
            hits = [e for e in entities if e["meta"]["symbol"] in wanted]
            return httpx.Response(200, json=hits)
        if path.endswith("/enrich/ranktwosided"):
            return httpx.Response(200, json=enrich)
        if path.endswith("/signatures/find"):
            return httpx.Response(200, json=signatures)
        return httpx.Response(404, text=f"unexpected path {path}")

    return handler


@pytest.mark.asyncio
async def test_lincs_find_reversers_end_to_end():
    transport = httpx.MockTransport(_lincs_handler())
    async with httpx.AsyncClient(transport=transport) as http:
        client = SigComLincsClient(client=http)
        result = await client.find_reversers(
            up_symbols=["IRAK1"], down_symbols=["MECP2", "BDNF"], limit=10
        )

    # Only the two reversers (negative z) survive; the mimicker is dropped.
    reversers = result["reversers"]
    assert {r["pert_name"] for r in reversers} == {"valproic-acid", "raloxifene"}
    strongest = min(reversers, key=lambda r: r["z_sum"])
    assert strongest["pert_name"] == "valproic-acid"
    assert strongest["z_sum"] == pytest.approx(-8.1)
    assert result["resolved_up"] == {"IRAK1": "uuid-IRAK1"}


@pytest.mark.asyncio
async def test_lincs_raises_when_no_genes_resolve():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/entities/find"):
            return httpx.Response(200, json=[])  # nothing resolves
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = SigComLincsClient(client=http)
        with pytest.raises(LincsError):
            await client.find_reversers(up_symbols=["NOPE"], down_symbols=["ZILCH"], limit=5)
