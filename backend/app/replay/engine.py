"""Replays the pre-generated window as a stream of events.

The brief's backend job (section 8): "replays the pre-generated transaction file
through the rule engine, streams score updates over WebSocket". The analysis is
already complete before the replay starts -- what streams is the *presentation*
of a finished, deterministic result in transaction-time order.

That ordering matters for the demo: the audience watches the score climb one
named rule at a time and the ring assemble on the graph, which is the whole
argument. But nothing is being decided live, so the demo cannot produce a
different answer on the night than it did in rehearsal.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterator

from ..analysis import Analysis


@dataclass(frozen=True)
class ReplayEvent:
    at: dt.datetime
    kind: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at.isoformat(), "kind": self.kind, **self.payload}


def build_events(analysis: Analysis, *, include_transactions: bool = True) -> list[ReplayEvent]:
    """Every event in the window, in timestamp order.

    Event kinds:

    ``transaction``   a transfer hits the feed
    ``rule_fired``    a rule fired; carries the score before and after
    ``action``        an account's band changed, so its next step changed
    ``ml_flag``       the anomaly model's verdict on an account
    ``ml_network``    a connected cluster of anomalous accounts
    ``complete``      end of window, with the closing summary
    """
    events: list[ReplayEvent] = []

    if include_transactions:
        for txn in analysis.ctx.transactions:
            events.append(
                ReplayEvent(
                    at=txn.timestamp,
                    kind="transaction",
                    payload={
                        "txn_id": txn.txn_id,
                        "from_account": txn.from_account,
                        "to_account": txn.to_account,
                        "amount": txn.amount,
                        "channel": txn.channel,
                    },
                )
            )

    for event in analysis.timeline():
        when = dt.datetime.fromisoformat(event["timestamp"])
        events.append(ReplayEvent(at=when, kind="rule_fired", payload=event))
        if event["crossed_into"]:
            score = analysis.scores[event["account_id"]]
            from ..engine.actions import action_for_account

            action = action_for_account(score)
            events.append(
                ReplayEvent(
                    at=when,
                    kind="action",
                    payload={
                        **action.to_dict(),
                        # The band as it was at this moment, not the final one:
                        # an account that later climbs higher still crossed
                        # *this* line here, and the demo narrates the crossing.
                        "code": event["band_code"],
                        "label": event["band_label"],
                        "score": event["score_after"],
                        "triggered_by": event["rule_id"],
                    },
                )
            )

    # The model runs on the completed window, so its findings land at the end.
    # Presenting them mid-stream would imply it was scoring transaction by
    # transaction, which is not what an unsupervised outlier detector does.
    if analysis.graph_enabled:
        for account_id in analysis.anomaly.anomalous_accounts:
            finding = analysis.anomaly.findings[account_id]
            events.append(
                ReplayEvent(
                    at=analysis.as_of,
                    kind="ml_flag",
                    payload={
                        "account_id": account_id,
                        "anomaly_score": finding.anomaly_score,
                        "rank": finding.rank,
                        "rule_score": analysis.score_of(account_id),
                        "top_features": finding.top_features,
                    },
                )
            )
        for network in analysis.networks:
            events.append(
                ReplayEvent(
                    at=analysis.as_of,
                    kind="ml_network",
                    payload={
                        "network_id": network.network_id,
                        "account_ids": network.account_ids,
                        "density": network.density,
                        "mean_anomaly": network.mean_anomaly,
                        "max_rule_score": network.max_rule_score,
                        "missed_by_rules": network.missed_by_rules,
                        "action_code": network.action_code,
                        "action_label": network.action_label,
                        "rationale": network.rationale,
                    },
                )
            )

    events.sort(key=lambda e: (e.at, _ORDER.get(e.kind, 99)))
    events.append(
        ReplayEvent(
            at=analysis.as_of,
            kind="complete",
            payload={
                "flagged_accounts": len(analysis.flagged_accounts),
                "missed_networks": len(analysis.missed_networks),
                "graph_enabled": analysis.graph_enabled,
            },
        )
    )
    return events


#: Tie-break order within one timestamp, so a transfer is shown arriving before
#: the rule it triggers, and the rule before the action it produces.
_ORDER = {"transaction": 0, "rule_fired": 1, "action": 2, "ml_flag": 3, "ml_network": 4}


def stream(events: list[ReplayEvent]) -> Iterator[dict[str, Any]]:
    for event in events:
        yield event.to_dict()
