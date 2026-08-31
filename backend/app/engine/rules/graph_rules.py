"""Graph / network rules: G1, G2, G3 (CLAUDE.md section 4).

These are the rules a per-transaction monitoring system cannot express, and
they are what the "rules-only" proof toggle in the UI switches off. All three
carry ``requires_graph = True``.
"""

from __future__ import annotations

import statistics
from collections import Counter

from ...models import RuleHit
from ..context import EvaluationContext
from ...graphlayer.community import communities, density, hub_of
from ...graphlayer.traversal import shortest_path_between, within_hops
from .base import Rule


class G1HighRiskProximity(Rule):
    rule_id = "G1"
    name = "High-risk proximity"
    category = "graph"
    points = 15
    description = "Connected to a known suspicious account within 2 hops."
    requires_graph = True

    hops = 2

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        """Proximity to a *previously reported* account.

        The watchlist is an input, never something the engine infers from its
        own scores. If G1 keyed on live scores it would be self-referential --
        one account crossing a threshold would cascade points to its
        neighbours, which would then cascade further, and no point in the final
        score would trace to an observation.
        """
        suspects = sorted(
            account_id
            for account_id, account in sorted(ctx.accounts.items())
            if account.known_suspicious
        )
        if not suspects or ctx.ugraph is None:
            return []

        hits: list[RuleHit] = []
        flagged: set[str] = set()
        for suspect in suspects:
            for account_id, distance in sorted(
                within_hops(ctx.ugraph, suspect, self.hops).items()
            ):
                if account_id in flagged or ctx.accounts[account_id].known_suspicious:
                    continue
                flagged.add(account_id)
                path = shortest_path_between(ctx.ugraph, account_id, suspect)
                # Date the hit to the transaction that closed the path, so the
                # replay shows it firing at the moment the link is created
                # rather than at the start of the window.
                when = _path_completed_at(ctx, path)
                hits.append(
                    self.hit(
                        account_id,
                        when,
                        (
                            f"{distance} hop{'s' if distance > 1 else ''} from "
                            f"{suspect}, an account flagged by a previous "
                            f"investigation."
                        ),
                        evidence_accounts=[suspect],
                        details={
                            "suspect": suspect,
                            "hops": distance,
                            "path": path,
                        },
                    )
                )
        return hits


def _path_completed_at(ctx: EvaluationContext, path: list[str]):
    """When the last edge on ``path`` first appeared."""
    latest = ctx.as_of
    stamps = []
    for left, right in zip(path, path[1:]):
        for a, b in ((left, right), (right, left)):
            if ctx.graph.has_edge(a, b):
                stamps.append(ctx.graph[a][b]["first_seen"])
    return max(stamps) if stamps else latest


class G2SharedIdentifiers(Rule):
    rule_id = "G2"
    name = "Shared identifiers"
    category = "graph"
    points = 20
    description = (
        "Multiple accounts share a device fingerprint, phone number or address."
    )
    requires_graph = True

    min_accounts = 3

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        hits: list[RuleHit] = []
        flagged: set[str] = set()

        for kind, owners in (
            ("device fingerprint", ctx.device_owners),
            ("phone number", ctx.phone_owners),
            ("address", ctx.address_owners),
        ):
            for identifier, accounts in sorted(owners.items()):
                if len(accounts) < self.min_accounts:
                    continue
                when = self._observed_at(ctx, kind, identifier, accounts)
                for account_id in accounts:
                    if account_id in flagged:
                        continue
                    flagged.add(account_id)
                    others = [a for a in accounts if a != account_id]
                    hits.append(
                        self.hit(
                            account_id,
                            when,
                            (
                                f"Shares a {kind} ({identifier}) with "
                                f"{len(others)} other account"
                                f"{'s' if len(others) != 1 else ''}: "
                                f"{', '.join(others)}."
                            ),
                            evidence_accounts=others,
                            details={
                                "identifier_type": kind,
                                "identifier": identifier,
                                "shared_with": others,
                            },
                        )
                    )
        return hits

    def _observed_at(self, ctx: EvaluationContext, kind: str, identifier: str, accounts: list[str]):
        """The moment the sharing became visible.

        For a device that is the session in which the *last* of the accounts
        appeared on it -- before then, the bank has not yet seen the overlap.
        Phones and addresses are static account attributes, so those are dated
        to the start of the observable window.
        """
        if kind != "device fingerprint":
            return ctx.transactions[0].timestamp if ctx.transactions else ctx.as_of
        first_seen: dict[str, object] = {}
        for session in ctx.dataset.device_sessions:
            if session.device_fingerprint != identifier:
                continue
            current = first_seen.get(session.account)
            if current is None or session.timestamp < current:  # type: ignore[operator]
                first_seen[session.account] = session.timestamp
        return max(first_seen.values()) if first_seen else ctx.as_of  # type: ignore[return-value]


class G3EmergingRing(Rule):
    rule_id = "G3"
    name = "Emerging ring"
    category = "graph"
    points = 35
    description = (
        "A cluster of more than 10 accounts moving on similar transaction "
        "timing and routing."
    )
    requires_graph = True

    min_cluster = 11  # "more than 10"
    min_density = 0.15
    #: Fraction of a cluster's internal transfers that must fall inside a
    #: two-hour band for its timing to count as coordinated.
    min_timing_concentration = 0.45

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        """Size alone is not a ring -- a bank has plenty of large communities.

        What separates a ring is that its members move on a *schedule*: the
        same hour, the same routing, cycle after cycle. So a community only
        fires if it is large, internally dense, and its internal transfers
        concentrate in a narrow time-of-day band.
        """
        if ctx.ugraph is None:
            return []
        hits: list[RuleHit] = []
        for group in communities(ctx.ugraph):
            if len(group) < self.min_cluster:
                continue
            if density(ctx.ugraph, group) < self.min_density:
                continue
            concentration, peak_hour, internal, on_schedule = self._timing(ctx, group)
            if concentration < self.min_timing_concentration:
                continue
            # Fire on the accounts that actually move on the shared schedule,
            # not on everyone Louvain happened to place in the same partition.
            # A community absorbs whatever is loosely attached to a ring -- the
            # account that funded it, a counterparty it paid once -- and those
            # accounts are not themselves evidence of a ring.
            participants = sorted(
                {t.from_account for t in on_schedule} | {t.to_account for t in on_schedule}
            )
            if len(participants) < self.min_cluster:
                continue
            hub = hub_of(ctx.ugraph, participants)
            when = max(t.timestamp for t in on_schedule)
            for account_id in participants:
                hits.append(
                    self.hit(
                        account_id,
                        when,
                        (
                            f"Member of a {len(participants)}-account cluster in which "
                            f"{concentration:.0%} of internal transfers occur around "
                            f"{peak_hour:02d}:00. Hub: {hub}."
                        ),
                        evidence_txn_ids=[t.txn_id for t in on_schedule],
                        evidence_accounts=[a for a in participants if a != account_id],
                        details={
                            "cluster_size": len(participants),
                            "hub": hub,
                            "timing_concentration": round(concentration, 3),
                            "peak_hour": peak_hour,
                            "density": round(density(ctx.ugraph, participants), 3),
                        },
                    )
                )
        return hits

    def _timing(self, ctx: EvaluationContext, group: list[str]):
        members = set(group)
        internal = [
            t
            for t in ctx.transactions
            if t.from_account in members and t.to_account in members
        ]
        if not internal:
            return 0.0, 0, internal, []
        hours = Counter(t.timestamp.hour for t in internal)
        peak_hour, _ = max(sorted(hours.items()), key=lambda kv: kv[1])
        on_schedule = [t for t in internal if t.timestamp.hour == peak_hour]
        return len(on_schedule) / len(internal), peak_hour, internal, on_schedule


def timing_regularity(timestamps) -> float:
    """Standard deviation of minute-of-hour, exposed for the copilot narrative."""
    minutes = [t.minute for t in timestamps]
    return statistics.pstdev(minutes) if len(minutes) > 1 else 0.0
