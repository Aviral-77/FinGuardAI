"""The Act 3 claim, pinned.

The demo asserts something specific and falsifiable: there is a mule network in
this data that the deterministic rules do not escalate, and the anomaly model
finds it anyway. That is not a slide -- it is these assertions.

If someone later weakens a rule threshold until the stealth ring trips a rule,
or tunes the model until it stops finding it, these tests fail and the claim
stops being made.
"""

from __future__ import annotations

import pytest

from app.analysis import run_analysis
from app.config import ML_MISSED_MAX_RULE_SCORE
from app.dataio import load_dataset
from app.generator import typologies as T


@pytest.fixture(scope="module")
def analysis():
    return run_analysis(load_dataset())


def test_no_rule_fires_on_the_stealth_ring(analysis):
    """Half the claim: the rules genuinely miss it.

    Not "scores below the threshold" -- *no rule fires at all*. Every member
    sits under every one of the eleven thresholds.
    """
    for account_id in T.STEALTH:
        hits = [h for h in analysis.hits if h.account_id == account_id]
        assert hits == [], f"{account_id} unexpectedly triggered {[h.rule_id for h in hits]}"
        assert analysis.score_of(account_id) == 0


def test_stealth_ring_would_be_allowed_by_the_rule_engine(analysis):
    """Every member lands in the band that takes no action at all."""
    for account_id in T.STEALTH:
        code, _ = analysis.band_of(account_id)
        assert code == "ALLOW"


def test_anomaly_model_finds_the_ring_as_a_network(analysis):
    """The other half: the model finds it, and finds it as a *network*."""
    missed = analysis.missed_networks
    assert missed, "the anomaly model found no network that the rules missed"

    stealth = set(T.STEALTH)
    matching = [n for n in missed if len(stealth & set(n.account_ids)) >= 6]
    assert matching, (
        "no MISSED_BY_RULES network contains the stealth ring; "
        f"networks found: {[(n.network_id, n.account_ids) for n in missed]}"
    )
    network = matching[0]
    assert network.max_rule_score < ML_MISSED_MAX_RULE_SCORE
    assert network.missed_by_rules is True
    assert len(network.account_ids) >= 4


def test_missed_network_carries_a_named_action(analysis):
    """An ML finding is still an alert, so it still needs a next step."""
    assert analysis.ml_actions, "a missed network produced no action"
    for action in analysis.ml_actions:
        assert action.code == "ML_REVIEW"
        assert action.source == "anomaly-model"
        assert action.label == "Manual fraud review"


def test_ml_findings_never_change_a_rule_score(analysis):
    """The brief's non-negotiable, enforced.

    Every point in every score must equal the sum of the distinct rules that
    fired on that account. If the anomaly score were ever folded in, this
    arithmetic would stop reconciling.
    """
    from app.engine.registry import RULES_BY_ID

    for account_id, score in analysis.scores.items():
        expected = min(100, sum(RULES_BY_ID[r].points for r in score.rule_ids))
        assert score.score == expected, f"{account_id} score does not reconcile to its rules"


def test_the_loud_ring_is_reported_as_already_escalated(analysis):
    """The contrast that makes the point.

    The model also flags the loud ring -- it is a conduit too. But that network
    is *not* marked missed, because the rules did escalate it. Without this the
    demo could not distinguish "the model found something new" from "the model
    found everything".
    """
    covering = [
        n
        for n in analysis.networks
        if T.RING_HUB in n.account_ids or T.PRIMARY_MULE in n.account_ids
    ]
    assert covering, "the anomaly model did not cluster the loud ring at all"
    assert any(not n.missed_by_rules for n in covering)


def test_explanations_are_concrete(analysis):
    """A flag an analyst cannot interrogate is not evidence."""
    for account_id in T.STEALTH:
        finding = analysis.anomaly.findings[account_id]
        if not (finding.is_anomalous or finding.is_elevated):
            continue
        assert finding.top_features, f"{account_id} flagged with no explanation"
        for feature in finding.top_features:
            assert feature["label"]
            assert abs(feature["z_score"]) >= 1.0
