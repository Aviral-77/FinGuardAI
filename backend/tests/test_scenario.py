"""Pins the demo. If these fail, the three-minute story has changed.

CLAUDE.md section 6 specifies exact outcomes: the victim lands around 35, the
primary mule crosses 65, and the ring node crosses 86 into a freeze. Those are
asserted here against a real engine run, so the demo cannot silently drift.
"""

from __future__ import annotations

import pytest

from app.analysis import run_analysis
from app.dataio import load_dataset
from app.generator import typologies as T


@pytest.fixture(scope="module")
def analysis():
    return run_analysis(load_dataset())


# --------------------------------------------------------------------------
# Scenario 1 -- the scripted ring
# --------------------------------------------------------------------------


def test_victim_lands_in_enhanced_monitoring(analysis):
    """The victim is a victim, not a suspect."""
    score = analysis.scores[T.VICTIM]
    assert score.score == 35
    assert score.band_label == "Enhanced monitoring"
    assert score.rule_ids == ["S1", "S3"]


def test_primary_mule_crosses_65(analysis):
    score = analysis.scores[T.PRIMARY_MULE]
    assert score.score == 65
    assert score.band_label == "Step-up authentication"
    assert set(score.rule_ids) == {"M1", "M2", "G2"}


def test_ring_hub_crosses_86_into_freeze(analysis):
    score = analysis.scores[T.RING_HUB]
    assert score.score >= 86
    assert score.band_label == "Temporary block / freeze"


def test_g3_is_the_rule_that_carries_the_hub_over_the_line(analysis):
    """The climax of the demo: the ring being *seen* is what triggers the freeze.

    Before G3 the hub must sit below 86, and G3 must be the firing that takes
    it above. If some other rule got there first the demo still freezes the
    account, but for the wrong reason, and the point about the graph layer is
    lost.
    """
    events = [e for e in analysis.timeline() if e["account_id"] == T.RING_HUB]
    crossing = [e for e in events if e["crossed_into"] == "FREEZE"]
    assert len(crossing) == 1, "the hub should cross into FREEZE exactly once"
    assert crossing[0]["rule_id"] == "G3"
    assert crossing[0]["score_before"] < 86 <= crossing[0]["score_after"]


def test_rules_fire_in_the_order_the_brief_specifies(analysis):
    """S3 -> S1 -> M1 -> M2 -> G2 -> G3, across victim, mule and hub.

    Relative order, not an exclusive sequence: the brief names the six rules
    that drive the visible score climb, and other rules legitimately fire in
    between (the hub also picks up G1 on its way to the freeze). What the demo
    needs is that these six arrive in this order.
    """
    scripted = ["S3", "S1", "M1", "M2", "G2", "G3"]
    watched = {T.VICTIM, T.PRIMARY_MULE, T.RING_HUB}
    order: list[str] = []
    for event in analysis.timeline():
        if (
            event["account_id"] in watched
            and event["rule_id"] in scripted
            and event["rule_id"] not in order
        ):
            order.append(event["rule_id"])
    assert order == scripted


def test_g3_fires_on_exactly_the_eleven_ring_accounts(analysis):
    members = sorted({h.account_id for h in analysis.hits if h.rule_id == "G3"})
    assert members == sorted(T.RING)


# --------------------------------------------------------------------------
# Scenario 2 -- account takeover
# --------------------------------------------------------------------------


def test_account_takeover_reaches_manual_review(analysis):
    score = analysis.scores[T.ATO_VICTIM]
    assert set(score.rule_ids) == {"A1", "A2", "S2"}
    assert score.score == 75
    assert score.band_label == "Manual fraud review"


# --------------------------------------------------------------------------
# Every rule is real
# --------------------------------------------------------------------------


def test_every_rule_fires_somewhere(analysis):
    """All eleven rules are implemented and demonstrably reachable."""
    fired = {h.rule_id for h in analysis.hits}
    expected = {"M1", "M2", "M3", "S1", "S2", "S3", "A1", "A2", "G1", "G2", "G3"}
    assert expected - fired == set(), f"never fired: {sorted(expected - fired)}"


def test_no_alert_leaves_without_a_named_action(analysis):
    """The brief's hard rule, asserted rather than trusted."""
    for action in analysis.actions + analysis.ml_actions:
        assert action.label and action.verb
        assert action.reason
