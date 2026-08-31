"""Mule-behaviour rules: M1, M2, M3 (CLAUDE.md section 4)."""

from __future__ import annotations

import datetime as dt
import statistics

from ...models import RuleHit
from ..context import EvaluationContext
from .base import Rule

#: Credits below this are ignored by M1. Without a floor, an account that
#: receives 200 rupees and spends 180 of it looks identical to a pass-through
#: mule, and the rule would fire on most of the retail population.
M1_MATERIAL_CREDIT = 25_000.0


class M1RapidFundMovement(Rule):
    rule_id = "M1"
    name = "Rapid fund movement"
    category = "mule"
    points = 25
    description = (
        "Funds credited, then more than 80% of the balance transferred out "
        "within 24 hours."
    )

    threshold_ratio = 0.80
    window = dt.timedelta(hours=24)

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for account_id in sorted(ctx.credits):
            debits = ctx.outgoing.get(account_id, ())
            if not debits:
                continue
            events = ctx.credits[account_id]
            for index, event in enumerate(events):
                if event.amount < M1_MATERIAL_CREDIT or event.balance_after <= 0:
                    continue
                target = event.balance_after * self.threshold_ratio
                cumulative = 0.0
                evidence: list[str] = []
                # An episode runs from this credit until either 24h elapse or
                # the next material credit lands. Without that second boundary
                # the window would absorb money that arrived *after* the credit
                # being judged, and the drained share could exceed 100% of the
                # balance it is measured against.
                deadline = event.timestamp + self.window
                next_credit = next(
                    (
                        later.timestamp
                        for later in events[index + 1 :]
                        if later.amount >= M1_MATERIAL_CREDIT
                    ),
                    None,
                )
                if next_credit is not None:
                    deadline = min(deadline, next_credit)
                for txn in debits:
                    if txn.timestamp < event.timestamp:
                        continue
                    if txn.timestamp > deadline:
                        break
                    cumulative += txn.amount
                    evidence.append(txn.txn_id)
                    if cumulative >= target:
                        share = cumulative / event.balance_after
                        hits.append(
                            self.hit(
                                account_id,
                                txn.timestamp,
                                (
                                    f"{share:.0%} of a {event.balance_after:,.0f} balance "
                                    f"left the account within "
                                    f"{(txn.timestamp - event.timestamp).total_seconds() / 3600:.0f}h "
                                    f"of a {event.amount:,.0f} credit."
                                ),
                                evidence_txn_ids=[event.txn_id, *evidence],
                                details={
                                    "balance_at_credit": round(event.balance_after, 2),
                                    "moved_out": round(cumulative, 2),
                                    "share": round(share, 4),
                                    "hours_to_clear": round(
                                        (txn.timestamp - event.timestamp).total_seconds() / 3600, 1
                                    ),
                                },
                            )
                        )
                        break
                # One firing per account is all that scores; stop at the first.
                if hits and hits[-1].account_id == account_id:
                    break
        return hits


class M2MultipleSourceAccounts(Rule):
    rule_id = "M2"
    name = "Multiple source accounts"
    category = "mule"
    points = 20
    description = (
        "Receives from more than 5 unique accounts in 7 days, with the incoming "
        "amounts clustered within plus or minus 20% of their mean."
    )

    min_unique_senders = 6  # "more than 5"
    window = dt.timedelta(days=7)
    band = 0.20
    min_clustered = 6

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for account_id in sorted(ctx.incoming):
            credits = ctx.incoming[account_id]
            if len(credits) < self.min_unique_senders:
                continue
            start = 0
            for end, txn in enumerate(credits):
                while credits[start].timestamp < txn.timestamp - self.window:
                    start += 1
                window = credits[start : end + 1]
                senders = {t.from_account for t in window}
                if len(senders) < self.min_unique_senders:
                    continue
                amounts = [t.amount for t in window]
                mean = statistics.fmean(amounts)
                if mean <= 0:
                    continue
                clustered = [
                    t for t in window if abs(t.amount - mean) / mean <= self.band
                ]
                if len(clustered) < self.min_clustered:
                    continue
                hits.append(
                    self.hit(
                        account_id,
                        txn.timestamp,
                        (
                            f"Received from {len(senders)} unique accounts in 7 days; "
                            f"{len(clustered)} of the credits sit within "
                            f"{self.band:.0%} of the {mean:,.0f} mean."
                        ),
                        evidence_txn_ids=[t.txn_id for t in clustered],
                        evidence_accounts=sorted({t.from_account for t in clustered}),
                        details={
                            "unique_senders": len(senders),
                            "clustered_credits": len(clustered),
                            "mean_incoming": round(mean, 2),
                        },
                    )
                )
                break
        return hits


class M3CircularTransactions(Rule):
    rule_id = "M3"
    name = "Circular transactions"
    category = "mule"
    points = 30
    description = (
        "Funds move among 3 or more connected accounts and return to the "
        "originating account within 72 hours."
    )
    requires_graph = True

    window = dt.timedelta(hours=72)
    min_cycle = 3
    max_cycle = 6

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        """Depth-first search over time-ordered edges.

        A cycle only counts when each hop happens *after* the previous one and
        the whole loop closes inside 72 hours -- money that happens to flow both
        ways between two businesses over a month is not round-tripping.
        """
        hits: list[RuleHit] = []
        flagged: set[str] = set()

        for origin in sorted(ctx.outgoing):
            if origin in flagged:
                continue
            for first in ctx.outgoing[origin]:
                found = self._walk(
                    ctx,
                    origin=origin,
                    current=first.to_account,
                    deadline=first.timestamp + self.window,
                    last_time=first.timestamp,
                    path=[origin, first.to_account],
                    txn_ids=[first.txn_id],
                )
                if found is None:
                    continue
                path, txn_ids, elapsed = found
                members = sorted(set(path))
                for member in members:
                    if member in flagged:
                        continue
                    flagged.add(member)
                    hits.append(
                        self.hit(
                            member,
                            first.timestamp + elapsed,
                            (
                                f"Funds moved through {len(members)} connected accounts "
                                f"and returned to {origin} in "
                                f"{elapsed.total_seconds() / 3600:.0f}h."
                            ),
                            evidence_txn_ids=txn_ids,
                            evidence_accounts=members,
                            details={
                                "cycle": path,
                                "hours": round(elapsed.total_seconds() / 3600, 1),
                            },
                        )
                    )
                break
        return hits

    def _walk(
        self,
        ctx: EvaluationContext,
        *,
        origin: str,
        current: str,
        deadline: dt.datetime,
        last_time: dt.datetime,
        path: list[str],
        txn_ids: list[str],
    ) -> tuple[list[str], list[str], dt.timedelta] | None:
        if len(path) > self.max_cycle:
            return None
        for txn in ctx.outgoing.get(current, ()):
            if txn.timestamp <= last_time or txn.timestamp > deadline:
                continue
            if txn.to_account == origin:
                if len(path) >= self.min_cycle:
                    start = deadline - self.window
                    return path, [*txn_ids, txn.txn_id], txn.timestamp - start
                continue
            if txn.to_account in path:
                continue
            found = self._walk(
                ctx,
                origin=origin,
                current=txn.to_account,
                deadline=deadline,
                last_time=txn.timestamp,
                path=[*path, txn.to_account],
                txn_ids=[*txn_ids, txn.txn_id],
            )
            if found is not None:
                return found
        return None
