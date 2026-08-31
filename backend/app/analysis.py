"""One pass over the dataset, producing everything the API serves.

Order matters and is fixed: rules -> scores -> actions -> graph -> anomaly
model -> anomaly networks. The model runs last and reads the rule scores only
to *report* whether a network was already escalated. It never feeds back into
them.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from functools import lru_cache

from .dataio import cached_dataset
from .engine.actions import Action, build_action_log
from .engine.context import EvaluationContext, build_context
from .engine.registry import rules_for
from .engine.scoring import band_for, score_accounts
from .graphlayer.community import hub_of
from .ml.features import build_features
from .ml.model import AnomalyResult, run_anomaly_model
from .ml.network import actions_for_networks, detect_networks
from .models import AccountScore, Dataset, MLNetwork, RuleHit


@dataclass
class Analysis:
    """The complete result of one analysis run."""

    dataset: Dataset
    ctx: EvaluationContext
    graph_enabled: bool
    hits: list[RuleHit]
    scores: dict[str, AccountScore]
    actions: list[Action]
    anomaly: AnomalyResult
    networks: list[MLNetwork] = field(default_factory=list)
    ml_actions: list[Action] = field(default_factory=list)

    # -- convenience -------------------------------------------------------

    def score_of(self, account_id: str) -> int:
        entry = self.scores.get(account_id)
        return entry.score if entry else 0

    def band_of(self, account_id: str) -> tuple[str, str]:
        band = band_for(self.score_of(account_id))
        return band.code, band.label

    @property
    def as_of(self) -> dt.datetime:
        return self.ctx.as_of

    @property
    def flagged_accounts(self) -> list[str]:
        return sorted(a for a, s in self.scores.items() if s.band_code != "ALLOW")

    @property
    def missed_networks(self) -> list[MLNetwork]:
        """Networks the anomaly model found that no rule escalated."""
        return [n for n in self.networks if n.missed_by_rules]

    def timeline(self) -> list[dict]:
        """Every rule firing in transaction-time order, with running scores.

        This is what the UI replays: the score climbing one named rule at a
        time. Built here rather than in the client so the sequence the demo
        shows is the same sequence the engine actually produced.
        """
        running: dict[str, int] = {}
        counted: dict[str, set[str]] = {}
        events: list[dict] = []
        for hit in sorted(self.hits, key=lambda h: (h.timestamp, h.rule_id, h.account_id)):
            seen = counted.setdefault(hit.account_id, set())
            before = running.get(hit.account_id, 0)
            counts = hit.rule_id not in seen
            if counts:
                seen.add(hit.rule_id)
                after = min(100, before + hit.points)
            else:
                after = before
            running[hit.account_id] = after
            band = band_for(after)
            events.append(
                {
                    "timestamp": hit.timestamp.isoformat(),
                    "account_id": hit.account_id,
                    "rule_id": hit.rule_id,
                    "rule_name": hit.rule_name,
                    "category": hit.category,
                    "points": hit.points if counts else 0,
                    "counted": counts,
                    "score_before": before,
                    "score_after": after,
                    "band_code": band.code,
                    "band_label": band.label,
                    "crossed_into": band.code if band_for(before).code != band.code else None,
                    "message": hit.message,
                    "evidence_txn_ids": hit.evidence_txn_ids,
                }
            )
        return events


def run_analysis(dataset: Dataset, *, graph_enabled: bool = True) -> Analysis:
    """Analyse a dataset end to end.

    ``graph_enabled=False`` drops the network rules and skips the anomaly layer
    entirely, reproducing what a conventional per-transaction system would have
    seen in the same window. That is a genuine re-run with a smaller rule set,
    not a filter over the full result -- which is the only way the comparison
    means anything.
    """
    ctx = build_context(dataset)

    hits: list[RuleHit] = []
    for rule in rules_for(graph_enabled=graph_enabled):
        hits.extend(rule.evaluate(ctx))
    hits.sort(key=lambda h: (h.timestamp, h.rule_id, h.account_id))

    scores = score_accounts(hits)
    actions = build_action_log(scores)

    if not graph_enabled:
        empty = run_anomaly_model(build_features(ctx).__class__(account_ids=[], rows=[]))
        return Analysis(
            dataset=dataset,
            ctx=ctx,
            graph_enabled=False,
            hits=hits,
            scores=scores,
            actions=actions,
            anomaly=empty,
            networks=[],
            ml_actions=[],
        )

    anomaly = run_anomaly_model(build_features(ctx))
    networks = detect_networks(ctx.ugraph, anomaly.findings, scores)
    ml_actions = actions_for_networks(networks, ctx.as_of)

    return Analysis(
        dataset=dataset,
        ctx=ctx,
        graph_enabled=True,
        hits=hits,
        scores=scores,
        actions=actions,
        anomaly=anomaly,
        networks=networks,
        ml_actions=ml_actions,
    )


@lru_cache(maxsize=2)
def cached_analysis(graph_enabled: bool = True) -> Analysis:
    """Analysis for the shipped dataset, memoised per rule-set variant.

    Two variants only -- full and rules-only -- so the proof toggle is instant
    in the demo rather than re-running the engine on every click.
    """
    return run_analysis(cached_dataset(), graph_enabled=graph_enabled)


def network_hub(analysis: Analysis, network: MLNetwork) -> str:
    return hub_of(analysis.ctx.ugraph.subgraph(network.account_ids), network.account_ids)
