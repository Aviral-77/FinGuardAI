"""Turns anomalous accounts into anomalous *networks*.

This is the Act 3 headline. On its own an Isolation Forest produces a list of
odd accounts, which is only marginally more useful than a list of odd
transactions -- it is still the analyst's job to notice that six of them pay
each other. Intersecting the model's output with the graph does that step:
anomalous accounts that are also *connected* to one another are a network.

The final move is the cross-check against the rule engine. A network whose
highest rule score never reached the review threshold is one the deterministic
engine did not escalate -- ``missed_by_rules``. That is the claim the demo
makes, and it is computed here rather than asserted in a slide.
"""

from __future__ import annotations

import datetime as dt

import networkx as nx

from ..config import ML_MIN_DENSITY, ML_MIN_NETWORK_SIZE, ML_MISSED_MAX_RULE_SCORE
from ..engine.actions import ACTION_EFFECTS, Action
from ..graphlayer.community import density, hub_of
from ..models import AccountScore, MLFinding, MLNetwork
from .explain import describe


def detect_networks(
    graph: nx.Graph,
    findings: dict[str, MLFinding],
    scores: dict[str, AccountScore],
) -> list[MLNetwork]:
    """Connected clusters of anomalous accounts.

    Uses connected components of the sub-graph induced on the flagged accounts,
    then filters on size and internal density. Density is what separates a ring
    from a chain of coincidences: four accounts that each happen to be odd and
    happen to touch one shared counterparty are not a network.
    """
    seeds = sorted(a for a, f in findings.items() if f.is_anomalous and a in graph)
    if not seeds:
        return []

    members = _expand(graph, findings, seeds)
    induced = graph.subgraph(members)
    networks: list[MLNetwork] = []

    for index, component in enumerate(
        sorted(
            (sorted(c) for c in nx.connected_components(induced)),
            key=lambda c: (-len(c), c[0]),
        )
    ):
        if len(component) < ML_MIN_NETWORK_SIZE:
            continue
        component_density = density(induced, component)
        if component_density < ML_MIN_DENSITY:
            continue

        mean_anomaly = sum(findings[a].anomaly_score for a in component) / len(component)
        rule_scores = [scores[a].score if a in scores else 0 for a in component]
        max_rule_score = max(rule_scores)
        missed = max_rule_score < ML_MISSED_MAX_RULE_SCORE

        networks.append(
            MLNetwork(
                network_id=f"MLN-{index + 1:02d}",
                account_ids=component,
                density=round(component_density, 4),
                mean_anomaly=round(mean_anomaly, 4),
                max_rule_score=max_rule_score,
                missed_by_rules=missed,
                action_code="ML_REVIEW",
                action_label="Manual fraud review",
                rationale=_rationale(component, findings, component_density, max_rule_score, missed, hub_of(induced, component)),
            )
        )
    return networks


#: How many rounds of expansion to run. Two is enough to close the gaps inside
#: a ring; more starts absorbing the ring's ordinary customers.
EXPANSION_ROUNDS = 2


def _expand(
    graph: nx.Graph, findings: dict[str, MLFinding], seeds: list[str]
) -> list[str]:
    """Grow the flagged set across accounts that are merely *elevated*.

    The contamination rate sets a deliberately strict bar, and one ring member
    scoring just under it would otherwise split the ring into two fragments,
    each too small to report. So membership of an already-seeded cluster is
    decided on a looser test: an elevated account joins if it is adjacent to at
    least two accounts already in the cluster.

    Requiring *two* connections is what stops this leaking. A single edge to a
    flagged account is something an ordinary customer can have -- being paid by
    a mule does not make you one -- whereas sitting between two of them is the
    structural position of a ring member.
    """
    members = set(seeds)
    for _ in range(EXPANSION_ROUNDS):
        additions: set[str] = set()
        for account_id in sorted(graph.nodes()):
            if account_id in members:
                continue
            finding = findings.get(account_id)
            if finding is None or not finding.is_elevated:
                continue
            links = sum(1 for n in graph.neighbors(account_id) if n in members)
            if links >= 2:
                additions.add(account_id)
        if not additions:
            break
        members |= additions
    return sorted(members)


def _rationale(
    component: list[str],
    findings: dict[str, MLFinding],
    component_density: float,
    max_rule_score: int,
    missed: bool,
    hub: str,
) -> list[str]:
    """The case for this network, in the order an analyst would want it."""
    shared = _shared_features(component, findings)
    lines = [
        f"{len(component)} accounts flagged by the anomaly model are connected "
        f"to one another (internal density {component_density:.0%}); hub is {hub}.",
    ]
    if shared:
        lines.append(
            "They share the same behavioural departures: "
            + ", ".join(shared)
            + "."
        )
    if missed:
        lines.append(
            f"No rule escalated any of them -- the highest rule score in the "
            f"cluster is {max_rule_score}, below the review threshold of "
            f"{ML_MISSED_MAX_RULE_SCORE}. A per-transaction system sees nothing here."
        )
    else:
        lines.append(
            f"The rule engine independently scored a member of this cluster at "
            f"{max_rule_score}, so this network was already escalated."
        )
    example = findings.get(hub)
    if example is not None:
        lines.append(f"{hub}: {describe(example.top_features)}")
    return lines


def _shared_features(component: list[str], findings: dict[str, MLFinding]) -> list[str]:
    """Feature departures common to most members -- the network's signature."""
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for account_id in component:
        finding = findings.get(account_id)
        if finding is None:
            continue
        for feature in finding.top_features:
            counts[feature["feature"]] = counts.get(feature["feature"], 0) + 1
            labels[feature["feature"]] = feature["label"]
    threshold = max(2, len(component) // 2)
    common = sorted(
        (name for name, count in counts.items() if count >= threshold),
        key=lambda name: (-counts[name], name),
    )
    return [labels[name] for name in common]


def actions_for_networks(
    networks: list[MLNetwork], as_of: dt.datetime
) -> list[Action]:
    """One named next step per ML-detected network.

    The brief's rule that no alert leaves without an action applies to the model
    lane too. ``ML_REVIEW`` is deliberately a distinct code from the rule bands:
    it says *why* the account is in front of an analyst, and it keeps the
    anomaly finding from being mistaken for a rule score.
    """
    effect = ACTION_EFFECTS["ML_REVIEW"]
    actions: list[Action] = []
    for network in networks:
        if not network.missed_by_rules:
            continue
        actions.append(
            Action(
                action_id=f"ACT-{network.network_id}",
                account_id=network.account_ids[0],
                code="ML_REVIEW",
                label=network.action_label,
                verb=effect["verb"],
                blocking=effect["blocking"],
                detail=effect["detail"],
                triggered_at=as_of,
                score=network.max_rule_score,
                source="anomaly-model",
                reason_rule_ids=[],
                reason=(
                    f"{len(network.account_ids)} connected accounts flagged by the "
                    f"anomaly model with no rule coverage "
                    f"({', '.join(network.account_ids)})."
                ),
            )
        )
    return actions
