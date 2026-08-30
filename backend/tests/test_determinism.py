"""Determinism -- the working principle the whole demo rests on.

CLAUDE.md section 10: "Pre-generate everything. The ring must form the same way
every run." A demo that is only *usually* right is one that fails on stage.
"""

from __future__ import annotations

import json

from app.analysis import run_analysis
from app.dataio import load_dataset
from app.generator.generate import build_world


def _fingerprint(analysis) -> str:
    """Canonical JSON of everything the UI would show."""
    return json.dumps(
        {
            "scores": {a: s.score for a, s in sorted(analysis.scores.items())},
            "hits": [
                [h.timestamp.isoformat(), h.rule_id, h.account_id, h.points]
                for h in analysis.hits
            ],
            "actions": [a.to_dict() for a in analysis.actions],
            "anomaly": {
                a: [f.rank, f.anomaly_score, f.is_anomalous]
                for a, f in sorted(analysis.anomaly.findings.items())
            },
            "networks": [
                [n.network_id, n.account_ids, n.missed_by_rules] for n in analysis.networks
            ],
        },
        sort_keys=True,
    )


def test_generator_is_reproducible():
    """Two builds of the world produce identical tables."""
    first, _ = build_world()
    second, _ = build_world()

    assert [a.account_id for a in first.accounts] == [a.account_id for a in second.accounts]
    assert [
        (t.txn_id, t.from_account, t.to_account, t.amount, t.timestamp)
        for t in first.transactions
    ] == [
        (t.txn_id, t.from_account, t.to_account, t.amount, t.timestamp)
        for t in second.transactions
    ]
    assert len(first.device_sessions) == len(second.device_sessions)
    assert len(first.beneficiaries) == len(second.beneficiaries)


def test_analysis_is_reproducible():
    """Two runs of the full pipeline, including the model, agree exactly."""
    dataset = load_dataset()
    assert _fingerprint(run_analysis(dataset)) == _fingerprint(run_analysis(dataset))


def test_committed_csvs_match_the_generator():
    """The checked-in data is what the generator produces.

    Guards against someone editing a CSV by hand, or changing the generator and
    forgetting to regenerate -- either of which would make the committed data
    and the code disagree.
    """
    generated, _ = build_world()
    loaded = load_dataset()

    assert len(generated.accounts) == len(loaded.accounts)
    assert len(generated.transactions) == len(loaded.transactions)
    assert [t.txn_id for t in generated.transactions] == [t.txn_id for t in loaded.transactions]
    assert [round(t.amount, 2) for t in generated.transactions] == [
        round(t.amount, 2) for t in loaded.transactions
    ]
