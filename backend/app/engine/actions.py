"""The action layer -- what the system *does* when rules break.

CLAUDE.md section 10: "make the action verb prominent in the UI, not the
score". An alert that says 87 is a number; an alert that says FREEZE is a
decision. Every alert leaving this engine carries a named next step, and every
step records the rules that justified it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from ..models import AccountScore

#: What each band actually does, beyond its label.
ACTION_EFFECTS: dict[str, dict[str, Any]] = {
    "ALLOW": {
        "verb": "Allow",
        "blocking": False,
        "detail": "Transaction proceeds. No analyst time consumed.",
    },
    "ENHANCED_MONITORING": {
        "verb": "Monitor",
        "blocking": False,
        "detail": "Account added to the watch queue; subsequent transfers re-scored on arrival.",
    },
    "STEP_UP_AUTH": {
        "verb": "Step up",
        "blocking": True,
        "detail": "Further transfers require additional verification before release.",
    },
    "MANUAL_REVIEW": {
        "verb": "Review",
        "blocking": True,
        "detail": "Outbound transfers held pending analyst decision. Case file generated.",
    },
    "FREEZE": {
        "verb": "Freeze",
        "blocking": True,
        "detail": "Account frozen and counterparties in the ring locked. Case file generated.",
    },
    # The ML lane. Deliberately its own code: an anomaly finding is not a rule
    # score, and collapsing the two would break the promise that every point
    # traces to a named rule.
    "ML_REVIEW": {
        "verb": "Review",
        "blocking": True,
        "detail": (
            "Anomaly model flagged a connected cluster that no rule covers. "
            "Routed to manual fraud review as an unruled network."
        ),
    },
}


@dataclass
class Action:
    """One decision, with the evidence that produced it."""

    action_id: str
    account_id: str
    code: str
    label: str
    verb: str
    blocking: bool
    detail: str
    triggered_at: dt.datetime
    score: int
    source: str  # "rules" | "anomaly-model"
    reason_rule_ids: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "account_id": self.account_id,
            "code": self.code,
            "label": self.label,
            "verb": self.verb,
            "blocking": self.blocking,
            "detail": self.detail,
            "triggered_at": self.triggered_at.isoformat(),
            "score": self.score,
            "source": self.source,
            "reason_rule_ids": self.reason_rule_ids,
            "reason": self.reason,
        }


def action_for_account(account: AccountScore) -> Action:
    """Map a scored account to its named next step.

    Pure table lookup on the band. No thresholds are re-litigated here.
    """
    effect = ACTION_EFFECTS[account.band_code]
    latest = max((h.timestamp for h in account.hits), default=dt.datetime.min)
    rule_ids = account.rule_ids
    return Action(
        action_id=f"ACT-{account.account_id}",
        account_id=account.account_id,
        code=account.band_code,
        label=account.band_label,
        verb=effect["verb"],
        blocking=effect["blocking"],
        detail=effect["detail"],
        triggered_at=latest,
        score=account.score,
        source="rules",
        reason_rule_ids=rule_ids,
        reason=(
            f"Score {account.score} from {len(rule_ids)} rule"
            f"{'s' if len(rule_ids) != 1 else ''}: {', '.join(rule_ids)}."
        )
        if rule_ids
        else "No rule fired.",
    )


def build_action_log(scores: dict[str, AccountScore]) -> list[Action]:
    """Actions for every account that any rule touched, newest last.

    Accounts in the ALLOW band are omitted: an allow is the absence of a
    decision, and listing 200 of them would bury the five that matter.
    """
    actions = [
        action_for_account(account)
        for _, account in sorted(scores.items())
        if account.band_code != "ALLOW"
    ]
    actions.sort(key=lambda a: (a.triggered_at, a.account_id))
    return actions
