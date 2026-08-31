"""Turns rule hits into scores, and scores into named actions.

The brief's non-negotiable lives here: **rules compute, thresholds decide**.
Nothing in this module makes a judgement call. A score is the sum of the point
values of the distinct rules that fired, and an action is a table lookup on
that score. No model, no weighting, no discretion.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import MAX_SCORE, SCORE_BANDS
from ..models import AccountScore, RuleHit


@dataclass(frozen=True)
class Band:
    code: str
    label: str
    lower: int
    upper: int


BANDS: tuple[Band, ...] = tuple(
    Band(code=code, label=label, lower=lower, upper=upper)
    for lower, upper, code, label in SCORE_BANDS
)


def band_for(score: int) -> Band:
    """The action band a score falls in. Total, so every score has an action.

    The brief's rule that "no alert may leave the system without a named next
    step" is enforced structurally: there is no path from a score to an empty
    action.
    """
    for band in BANDS:
        if band.lower <= score <= band.upper:
            return band
    return BANDS[-1] if score > BANDS[-1].upper else BANDS[0]


def score_accounts(hits: list[RuleHit]) -> dict[str, AccountScore]:
    """Aggregate hits into one score per account.

    A rule scores **once per account** no matter how many times it fires. The
    brief assigns each rule a single point value; letting a rule stack would
    make the same behaviour worth an arbitrary amount depending on how finely
    the data happened to be sliced, and would break the audit chain, since the
    total would no longer be readable off the list of rule names.

    Additional firings are still kept in ``hits`` as evidence -- they are
    visible to the investigator, they just do not add points.
    """
    grouped: dict[str, list[RuleHit]] = {}
    for hit in sorted(hits, key=lambda h: (h.timestamp, h.rule_id, h.account_id)):
        grouped.setdefault(hit.account_id, []).append(hit)

    scored: dict[str, AccountScore] = {}
    for account_id in sorted(grouped):
        account_hits = grouped[account_id]
        counted: dict[str, int] = {}
        for hit in account_hits:
            counted.setdefault(hit.rule_id, hit.points)
        total = min(MAX_SCORE, sum(counted.values()))
        band = band_for(total)
        scored[account_id] = AccountScore(
            account_id=account_id,
            score=total,
            band_code=band.code,
            band_label=band.label,
            hits=account_hits,
        )
    return scored


def score_breakdown(account: AccountScore) -> list[dict]:
    """Per-rule contribution, in firing order -- the audit trail for a score."""
    seen: set[str] = set()
    rows: list[dict] = []
    running = 0
    for hit in account.hits:
        counts = hit.rule_id not in seen
        if counts:
            seen.add(hit.rule_id)
            running = min(MAX_SCORE, running + hit.points)
        rows.append(
            {
                "rule_id": hit.rule_id,
                "rule_name": hit.rule_name,
                "category": hit.category,
                "points": hit.points if counts else 0,
                "counted": counts,
                "running_score": running,
                "timestamp": hit.timestamp.isoformat(),
                "message": hit.message,
                "evidence_txn_ids": hit.evidence_txn_ids,
            }
        )
    return rows
