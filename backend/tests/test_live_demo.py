"""Pins the DEMO-SPEC three-beat story against the live API.

These assertions are the demo: Beat 0 flags nothing, Beat 1 lands the victim at
35 with no action available, Beat 2 carries the ring hub across 86 and forms an
11-account ring, the freeze then blocks a further transfer with 409, and reset
returns to Beat 0. If any of these break, the stage demo has changed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.post("/api/demo/reset")
        yield c


def test_beat0_flags_nothing(client):
    snap = client.post("/api/demo/reset").json()
    assert snap["flagged"] == []
    assert snap["ring"] is None
    assert snap["monitored_accounts"] > 200


def test_beat1_victim_is_monitored_not_actioned(client):
    client.post("/api/demo/beat/1", params={"stagger_ms": 0})
    victim = client.get("/api/account/ACC-V001").json()
    assert victim["score"] == 35
    assert victim["band_code"] == "ENHANCED_MONITORING"
    assert victim["actionable"] is False
    assert "Insufficient evidence" in victim["evidence_note"]
    # The most important beat: a single unusual transfer is not a freeze.
    assert not client.get("/api/state").json()["ring"]


def test_beat2_forms_the_ring_and_crosses_86(client):
    client.post("/api/demo/beat/1", params={"stagger_ms": 0})
    client.post("/api/demo/beat/2", params={"stagger_ms": 0})

    hub = client.get("/api/account/ACC-R001").json()
    assert hub["score"] >= 86
    assert hub["band_code"] == "FREEZE"
    assert hub["actionable"] is True

    ring = client.get("/api/state").json()["ring"]
    assert ring is not None
    assert ring["count"] == 11
    assert ring["value_in_motion"] > 0


def test_score_reconciles_to_rules_live(client):
    client.post("/api/demo/beat/1", params={"stagger_ms": 0})
    client.post("/api/demo/beat/2", params={"stagger_ms": 0})
    hub = client.get("/api/account/ACC-R001").json()
    counted = sum(row["points"] for row in hub["breakdown"] if row["counted"])
    assert counted == hub["score"]


def test_freeze_blocks_further_transfers(client):
    client.post("/api/demo/beat/1", params={"stagger_ms": 0})
    client.post("/api/demo/beat/2", params={"stagger_ms": 0})
    client.post("/api/account/ACC-M001/freeze")

    blocked = client.post(
        "/api/transaction",
        json={"from_account": "ACC-F001", "to_account": "ACC-M001", "amount": 50000},
    )
    assert blocked.status_code == 409
    assert blocked.json()["accepted"] is False
    assert "frozen" in blocked.json()["reason"].lower()


def test_reset_returns_to_beat0(client):
    client.post("/api/demo/beat/1", params={"stagger_ms": 0})
    client.post("/api/demo/beat/2", params={"stagger_ms": 0})
    snap = client.post("/api/demo/reset").json()
    assert snap["flagged"] == []
    assert snap["ring"] is None


def test_pdf_report_downloads(client):
    client.post("/api/demo/beat/1", params={"stagger_ms": 0})
    client.post("/api/demo/beat/2", params={"stagger_ms": 0})
    pdf = client.get("/api/account/ACC-R001/report.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"


def test_no_ml_in_the_live_demo(client):
    """The stage demo is rules-only: no anomaly networks are computed."""
    client.post("/api/demo/beat/1", params={"stagger_ms": 0})
    client.post("/api/demo/beat/2", params={"stagger_ms": 0})
    hub = client.get("/api/account/ACC-R001").json()
    # Every point is a rule; there is no anomaly contribution on this path.
    assert all(row["rule_id"] for row in hub["breakdown"])
