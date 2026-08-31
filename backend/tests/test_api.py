"""API smoke tests, including the proof toggle and the replay stream."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["accounts"] > 200


def test_rules_endpoint_lists_all_eleven(client):
    body = client.get("/api/rules").json()
    assert len(body["items"]) == 11
    assert {r["rule_id"] for r in body["items"]} == {
        "M1", "M2", "M3", "S1", "S2", "S3", "A1", "A2", "G1", "G2", "G3",
    }
    assert len(body["bands"]) == 5


def test_graph_returns_nodes_and_edges(client):
    body = client.get("/api/graph").json()
    assert len(body["nodes"]) > 200
    assert body["edges"]
    frozen = [n for n in body["nodes"] if n["band_code"] == "FREEZE"]
    assert frozen, "no account reaches the freeze band"


def test_ml_networks_include_a_missed_one(client):
    body = client.get("/api/ml/networks").json()
    assert body["missed_count"] >= 1
    missed = [n for n in body["items"] if n["missed_by_rules"]]
    assert missed
    assert missed[0]["max_rule_score"] < 51
    assert missed[0]["recommended_action"]["code"] == "ML_REVIEW"


def test_comparison_shows_the_ring_only_under_the_full_engine(client):
    """The proof toggle, asserted.

    Rules-only must freeze nothing: the ring is invisible to per-transaction
    monitoring, which is the claim the demo's most persuasive moment rests on.
    """
    body = client.get("/api/comparison").json()
    assert body["rules_only"]["frozen"] == []
    assert body["full"]["frozen"], "the full engine should freeze the ring"
    assert len(body["ring_accounts_caught_by_full"]) > len(
        body["ring_accounts_caught_by_rules_only"]
    )
    assert body["missed_networks"]


def test_copilot_case_reconciles_to_its_rules(client):
    body = client.get("/api/copilot/ACC-R001").json()
    assert body["score"] == 95
    assert body["recommended_action"]["code"] == "FREEZE"
    counted = sum(row["points"] for row in body["breakdown"] if row["counted"])
    assert counted == body["score"]


def test_copilot_markdown_renders(client):
    text = client.get("/api/copilot/ACC-R001/markdown").text
    assert "# Case file: ACC-R001" in text
    assert "Score breakdown" in text


def test_unknown_account_is_404(client):
    assert client.get("/api/copilot/ACC-NOPE").status_code == 404


def test_replay_stream_reaches_the_freeze_and_the_missed_network(client):
    """Walk the whole replay and check the two beats the demo needs."""
    with client.websocket_connect("/ws/replay") as ws:
        ws.send_json({"cmd": "start", "speed": 1_000_000, "graph_enabled": True})
        kinds: dict[str, int] = {}
        freeze_by_g3 = False
        missed = 0
        for _ in range(5000):
            message = ws.receive_json()
            kind = message.get("kind")
            kinds[kind] = kinds.get(kind, 0) + 1
            if kind == "action" and message.get("code") == "FREEZE":
                if message.get("triggered_by") == "G3":
                    freeze_by_g3 = True
            if kind == "ml_network" and message.get("missed_by_rules"):
                missed += 1
            if kind == "complete":
                break
        else:
            pytest.fail("replay never completed")

    assert kinds["transaction"] > 500
    assert kinds["rule_fired"] > 10
    assert freeze_by_g3, "no account was frozen by G3"
    assert missed >= 1
