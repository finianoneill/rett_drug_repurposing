"""FastAPI route tests, including SSE event sequence on /repurpose.

These do not hit live APIs. /repurpose's disease-resolution path prefers the
local DuckDB lookup, so seeding a populated store and pointing the app at it
avoids any Open Targets network call.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rett_repurposing.config import get_settings
from rett_repurposing.store.build import build


@pytest.fixture
def populated_duckdb(
    tmp_path: Path,
    opentargets_fixtures,
    chembl_fixture,
) -> Path:
    """Build a real DuckDB at a temp path using the test JSON fixtures."""
    ot_dir = tmp_path / "opentargets"
    ch_dir = tmp_path / "chembl"
    ot_dir.mkdir()
    ch_dir.mkdir()
    (ot_dir / "disease_targets.json").write_text(
        json.dumps(opentargets_fixtures["disease_targets"])
    )
    (ot_dir / "drug_candidates.json").write_text(
        json.dumps(opentargets_fixtures["drug_candidates"])
    )
    (ch_dir / "molecules.json").write_text(json.dumps(chembl_fixture))

    db_path = tmp_path / "rett_repurposing.duckdb"
    build(ot_dir, ch_dir, db_path)
    return db_path


@pytest.fixture
def client(
    populated_duckdb: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("DUCKDB_PATH", str(populated_duckdb))
    get_settings.cache_clear()
    from rett_repurposing.api.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture
def empty_db_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Client with an unpopulated DuckDB path so health reports not-ready."""
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "missing.duckdb"))
    get_settings.cache_clear()
    from rett_repurposing.api.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _parse_sse_stream(raw: str) -> list[dict[str, str]]:
    """Parse an SSE stream into a list of {event, data} dicts."""
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in raw.splitlines():
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith(":"):
            # SSE comment / heartbeat — ignore
            continue
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:") :].strip()
    if current:
        events.append(current)
    return events


def test_health_with_populated_store(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["duckdb_ready"] is True


def test_health_with_no_store(empty_db_client: TestClient) -> None:
    response = empty_db_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["duckdb_ready"] is False


def test_repurpose_streams_expected_event_sequence(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/repurpose",
        json={"disease": "Rett syndrome"},
    ) as response:
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "no-cache"
        assert "text/event-stream" in response.headers.get("content-type", "")
        body = "".join(response.iter_text())

    events = _parse_sse_stream(body)
    event_types = [e.get("event") for e in events]

    # First event is a status indicating disease resolution.
    assert event_types[0] == "status"
    first_payload = json.loads(events[0]["data"])
    assert first_payload["phase"] == "resolving_disease"

    assert "candidate" in event_types
    assert event_types[-1] == "complete"

    final_payload = json.loads(events[-1]["data"])
    candidate_count = sum(1 for e in events if e.get("event") == "candidate")
    assert final_payload["total"] == candidate_count
    assert final_payload["strategies_run"] == ["target_based"]


def test_repurpose_emits_candidate_payloads_matching_pydantic(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/repurpose",
        json={"disease": "MONDO_0010726"},  # exercise EFO-ID resolution path
    ) as response:
        body = "".join(response.iter_text())

    events = _parse_sse_stream(body)
    candidate_events = [e for e in events if e.get("event") == "candidate"]
    assert len(candidate_events) >= 1

    sample = json.loads(candidate_events[0]["data"])
    # Required fields per `Candidate` Pydantic model
    for required in ("drug", "target", "score", "score_components", "evidence", "strategy"):
        assert required in sample
    assert sample["strategy"] == "target_based"


def test_repurpose_unknown_disease_emits_error(empty_db_client: TestClient) -> None:
    """Empty DuckDB forces OT lookup, which we don't want hitting the network.
    A clearly-bogus disease string ensures no live match either way; OT will
    typically respond with no hits and the API converts that to an error event.

    NOTE: this test makes a live OT call. Marked integration so it can be
    skipped in CI if needed.
    """
    pytest.skip("Skipped to avoid live OT call; covered by test_fetchers")
