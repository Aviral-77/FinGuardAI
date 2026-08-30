"""Per-account behavioural features for the anomaly model.

These are standard money-mule indicators: pass-through behaviour traced through
the account, how long funds are held, how *regular* that behaviour is, and the
shape of the account's counterparty graph. They describe how a conduit account
behaves in general -- they were not reverse-engineered from the planted ring,
and the loud ring, the takeover and ordinary busy businesses all score on them
too.

Deliberately excluded: everything the rule engine keys on. No unique-sender
counts in a 7-day window, no shared-identifier flags, no >80%-in-24h test. If
the model reused the rules' own signals it could only re-find what the rules
already caught, and the Act 3 result would be circular.

``FEATURE_NAMES`` fixes the column order; the Isolation Forest depends on it.
"""

from __future__ import annotations

import statistics
from collections import Counter, deque
from dataclasses import dataclass

import networkx as nx

from ..engine.context import EvaluationContext

FEATURE_NAMES: tuple[str, ...] = (
    "conduit_ratio",
    "paired_flow_fraction",
    "pair_ratio_cv",
    "pair_delay_median_h",
    "pair_delay_cv",
    "hour_concentration",
    "credit_interval_cv",
    "fan_symmetry",
    "counterparty_churn",
    "amount_cv",
    "round_amount_fraction",
    "night_fraction",
    "txn_count",
    "degree",
    "clustering",
    "account_age_days",
)

FEATURE_LABELS: dict[str, str] = {
    "conduit_ratio": "share of incoming funds passed back out",
    "paired_flow_fraction": "share of credits followed by a matching onward transfer",
    "pair_ratio_cv": "consistency of the fraction forwarded each time",
    "pair_delay_median_h": "typical time funds are held before moving on",
    "pair_delay_cv": "regularity of that holding time",
    "hour_concentration": "share of activity in a single hour of the day",
    "credit_interval_cv": "regularity of the gaps between incoming credits",
    "fan_symmetry": "balance between number of senders and receivers",
    "counterparty_churn": "share of counterparties dealt with only once or twice",
    "amount_cv": "variability of transaction amounts",
    "round_amount_fraction": "share of transfers in round figures",
    "night_fraction": "share of activity between midnight and 6am",
    "txn_count": "total transactions",
    "degree": "number of distinct counterparties",
    "clustering": "interconnection between its counterparties",
    "account_age_days": "account age at the start of the window",
}

FEATURE_UNITS: dict[str, str] = {
    "conduit_ratio": "ratio",
    "paired_flow_fraction": "ratio",
    "pair_ratio_cv": "ratio",
    "pair_delay_median_h": "hours",
    "pair_delay_cv": "ratio",
    "hour_concentration": "ratio",
    "credit_interval_cv": "ratio",
    "fan_symmetry": "ratio",
    "counterparty_churn": "ratio",
    "amount_cv": "ratio",
    "round_amount_fraction": "ratio",
    "night_fraction": "ratio",
    "txn_count": "count",
    "degree": "count",
    "clustering": "ratio",
    "account_age_days": "days",
}

#: Features where a *low* value is the suspicious direction, because they
#: measure irregularity. Scripted behaviour is regular; people are not.
LOW_IS_SUSPICIOUS: frozenset[str] = frozenset(
    {"pair_ratio_cv", "pair_delay_cv", "amount_cv", "credit_interval_cv"}
)


@dataclass(slots=True)
class FeatureTable:
    account_ids: list[str]
    rows: list[list[float]]

    def as_mapping(self) -> dict[str, dict[str, float]]:
        return {
            account_id: dict(zip(FEATURE_NAMES, row))
            for account_id, row in zip(self.account_ids, self.rows)
        }


def _cv(values: list[float]) -> float:
    """Coefficient of variation. Near zero means a metronome."""
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    if mean == 0:
        return 0.0
    return statistics.pstdev(values) / abs(mean)


#: A debit counts as forwarding a credit if it is this share of it. The band is
#: wide on purpose -- a mule keeps a cut, and fees and rounding move the rest.
PAIR_MIN_RATIO = 0.45
PAIR_MAX_RATIO = 0.99
#: And if it follows within this long. Beyond a few days the link is a guess.
PAIR_MAX_DELAY_H = 96.0
#: Below this many pairs the regularity measures are noise, so they are reported
#: as "ordinary" rather than as a suspiciously perfect zero. Without this, every
#: account with one pair would look like a metronome.
MIN_PAIRS_FOR_REGULARITY = 3
NEUTRAL_CV = 0.60


def _pair_flows(credits, debits) -> tuple[int, list[float], list[float]]:
    """Match each credit to the onward transfer that forwards it.

    A pass-through account is defined by *pairing*: money arrives, and a similar
    amount leaves shortly after, over and over. Comparing totals cannot see
    this -- an account can credit and debit the same sum without any individual
    credit being forwarded -- and neither can a threshold rule, because no
    single pair is remarkable. What gives a conduit away is that the pairing
    holds every time, at the same fraction, after the same delay.

    Each debit is consumed at most once, earliest first, so one large outgoing
    payment cannot be counted as forwarding several credits.

    Returns ``(pair_count, ratios, delays_in_hours)``.
    """
    used: set[str] = set()
    ratios: list[float] = []
    delays: list[float] = []

    for credit in credits:
        for debit in debits:
            if debit.txn_id in used or debit.timestamp <= credit.timestamp:
                continue
            delay = (debit.timestamp - credit.timestamp).total_seconds() / 3600.0
            if delay > PAIR_MAX_DELAY_H:
                break  # debits are time-ordered: nothing later can match either
            ratio = debit.amount / credit.amount if credit.amount else 0.0
            if PAIR_MIN_RATIO <= ratio <= PAIR_MAX_RATIO:
                used.add(debit.txn_id)
                ratios.append(ratio)
                delays.append(delay)
                break
    return len(ratios), ratios, delays


def _regularity(values: list[float]) -> float:
    """Coefficient of variation, or a neutral value when there is too little."""
    if len(values) < MIN_PAIRS_FOR_REGULARITY:
        return NEUTRAL_CV
    return _cv(values)


def build_features(ctx: EvaluationContext) -> FeatureTable:
    """One row per account with any activity, in sorted account order."""
    clustering = nx.clustering(ctx.ugraph) if ctx.ugraph is not None else {}
    window_start = ctx.window_start

    account_ids: list[str] = []
    rows: list[list[float]] = []

    for account_id in sorted(ctx.accounts):
        credits = ctx.incoming.get(account_id, [])
        debits = ctx.outgoing.get(account_id, [])
        everything = sorted(credits + debits, key=lambda t: (t.timestamp, t.txn_id))
        if not everything:
            continue

        total_in = sum(t.amount for t in credits)
        total_out = sum(t.amount for t in debits)
        conduit_ratio = min(total_out / total_in, 2.0) if total_in > 0 else 0.0

        pair_count, pair_ratios, pair_delays = _pair_flows(credits, debits)
        paired_fraction = pair_count / len(credits) if credits else 0.0

        hours = Counter(t.timestamp.hour for t in everything)
        hour_concentration = max(hours.values()) / len(everything)

        credit_gaps = [
            (b.timestamp - a.timestamp).total_seconds() / 3600.0
            for a, b in zip(credits, credits[1:])
        ]

        senders = {t.from_account for t in credits}
        receivers = {t.to_account for t in debits}
        widest = max(len(senders), len(receivers))
        fan_symmetry = (min(len(senders), len(receivers)) / widest) if widest else 0.0

        counterparties: Counter[str] = Counter()
        for txn in credits:
            counterparties[txn.from_account] += 1
        for txn in debits:
            counterparties[txn.to_account] += 1
        churn = (
            sum(1 for count in counterparties.values() if count <= 2) / len(counterparties)
            if counterparties
            else 0.0
        )

        amounts = [t.amount for t in everything]
        account = ctx.accounts[account_id]

        account_ids.append(account_id)
        rows.append(
            [
                round(conduit_ratio, 6),
                round(paired_fraction, 6),
                round(_regularity(pair_ratios), 6),
                round(statistics.median(pair_delays) if pair_delays else 0.0, 4),
                round(_regularity(pair_delays), 6),
                round(hour_concentration, 6),
                round(_cv(credit_gaps), 6),
                round(fan_symmetry, 6),
                round(churn, 6),
                round(_cv(amounts), 6),
                round(sum(1 for a in amounts if a % 1000 == 0) / len(amounts), 6),
                round(sum(1 for t in everything if t.timestamp.hour < 6) / len(everything), 6),
                float(len(everything)),
                float(ctx.ugraph.degree(account_id)) if ctx.ugraph is not None else 0.0,
                round(float(clustering.get(account_id, 0.0)), 6),
                float((window_start.date() - account.open_date).days),
            ]
        )

    return FeatureTable(account_ids=account_ids, rows=rows)
