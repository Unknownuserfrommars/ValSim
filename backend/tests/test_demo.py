from collections import Counter
import json
from time import monotonic, sleep

from fastapi.testclient import TestClient
import pytest

from backend.valsim.api import SEED_DIR, make_app
from backend.valsim.model import observed_standings
from backend.valsim.players import player_directory
from backend.valsim.schema import Condition, Scenario, Snapshot
from backend.valsim.simulation import run


DEMO = SEED_DIR / "demo_group_a.json"
EVENT = "/v1/events/valsim-demo-group-a"


@pytest.fixture()
def client(tmp_path):
    with TestClient(make_app(tmp_path / "demo.sqlite3")) as app:
        yield app


def completed_job(client, config):
    response = client.post("/v1/simulations", json=config)
    assert response.status_code in (200, 202)
    location = response.headers["location"]
    deadline = monotonic() + 8
    while monotonic() < deadline:
        job = client.get(location).json()["data"]
        if job["status"] == "complete":
            return job
        assert job["status"] != "failed", job["error"]
        sleep(.03)
    pytest.fail("Simulation failed to complete")


@pytest.mark.parametrize("group", ["a", "b"])
def test_demo_is_complete_and_reproducible(group):
    snapshot = Snapshot.model_validate_json((SEED_DIR / f"demo_group_{group}.json").read_bytes())
    assert snapshot.source.permission == "fictional_demo"
    assert len(snapshot.teams) == 6
    assert Counter(match.status for match in snapshot.fixtures) == {"completed": 9, "scheduled": 6}
    before = observed_standings(snapshot)
    assert sum(row["wins"] for row in before) == 9

    directory = player_directory(snapshot)
    assert len(directory.list()) == 30
    assert len(directory.pack.group_series) == 9
    assert all(profile["primary_role"] for profile in directory.list())

    config = Scenario(snapshot_id=snapshot.id, scope="remaining_group")
    forecast = run(snapshot, config)
    assert forecast == run(snapshot, config)
    assert observed_standings(snapshot) == before
    assert forecast["output"]["locked_fixture_count"] == 9
    assert forecast["output"]["fixture_count"] == 6
    for row in forecast["output"]["teams"]:
        assert sum(row["ranks"]) == pytest.approx(1.0)


def test_manual_veto_as_well_as_locked_matches():
    snapshot = Snapshot.model_validate_json(DEMO.read_bytes())
    upcoming = next(item for item in snapshot.fixtures if item.status == "scheduled")
    legal = snapshot.rules.map_pool[:-1]
    config = Scenario(snapshot_id=snapshot.id, scope="match", fixture_id=upcoming.id, iterations=1000,
                      conditions=(Condition(fixture_id=upcoming.id, veto=legal),))
    result = run(snapshot, config)["output"]
    assert [item["map"] for item in result["veto"]] == list(snapshot.rules.map_pool)
    assert sum(row["probability"] for row in result["scores"]) == pytest.approx(1.0)
    locked = next(match for match in snapshot.fixtures if match.status == "completed")
    with pytest.raises(ValueError, match="cannot be changed"):
        run(snapshot, Scenario(snapshot_id=snapshot.id, scope="remaining_group",
                               conditions=(Condition(fixture_id=locked.id, score=(2, 0)),)))


def test_directory_group_switching_and_disclaimer(client):
    events = client.get("/v1/events").json()["data"]
    assert events["total"] == 2
    assert {item["data"]["stage"] for item in events["items"]} == {"Group A", "Group B"}
    profile = client.get(EVENT + "/players/rly-p1").json()["data"]
    assert profile["primary_role"] == "Duelist"
    assert profile["stats"]["series"] == 3
    assert len(profile["facets"]) == 7
    assert all(1 <= facet["score"] <= 99 for facet in profile["facets"])
    assert client.get("/v1/events/valsim-demo-group-b/players/rly-p1").status_code == 404
    assert "unofficial" in client.get("/disclaimer").text


def test_revision_compare_and_export(client):
    base = client.get(EVENT).json()
    config = {"snapshot_id": base["meta"]["snapshot_id"], "scope": "remaining_group",
              "iterations": 1000, "seed": 2402}
    fixture = next(item for item in base["data"]["fixtures"] if item["status"] == "scheduled")
    baseline = completed_job(client, config)
    scenario = completed_job(client, {**config, "conditions": [{"fixture_id": fixture["id"], "score": [2, 0]}]})
    path = "/v1/simulations/" + baseline["id"]
    comparison = client.post(path + "/compare", json={"conditioned_id": scenario["id"]})
    assert comparison.status_code == 200
    assert len(comparison.json()["data"]) == 6
    exported = client.get(path + "/export")
    assert exported.json()["data"] == baseline
    assert exported.json()["meta"]["input_hash"] == base["meta"]["input_hash"]

    updated = json.loads(DEMO.read_bytes())
    updated["id"] = "demo-revision"
    assert client.post("/v1/imports", json=updated).status_code == 201
    assert client.get(EVENT).json()["meta"]["snapshot_id"] == "demo-revision"
    assert client.get(path).json()["data"] == baseline
