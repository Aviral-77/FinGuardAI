"""The rule contract.

Every rule is a small, independently testable object with a fixed point value
taken straight from CLAUDE.md section 4. Nothing here computes a score: rules
emit :class:`~app.models.RuleHit` objects and ``app.engine.scoring`` adds them
up. That separation is what keeps the audit chain intact -- a score is never
anything but the sum of named rules.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from typing import Any

from ...models import RuleHit
from ..context import EvaluationContext


class Rule(ABC):
    """Base class for all detection rules."""

    #: Short identifier used in the UI and the audit trail, e.g. "M1".
    rule_id: str
    #: Human-readable name from the brief.
    name: str
    #: One of: mule | scam | takeover | graph
    category: str
    #: Points added to an account's score. Fixed by the brief.
    points: int
    #: One-line statement of what the rule looks for, shown in the rules panel.
    description: str
    #: Whether this rule needs the network view. The "rules-only" proof toggle
    #: switches these off to show what per-transaction monitoring would miss.
    requires_graph: bool = False

    @abstractmethod
    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        """Return every firing of this rule across the dataset."""

    # -- helpers ----------------------------------------------------------

    def hit(
        self,
        account_id: str,
        timestamp: dt.datetime,
        message: str,
        *,
        evidence_txn_ids: list[str] | None = None,
        evidence_accounts: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> RuleHit:
        return RuleHit(
            rule_id=self.rule_id,
            rule_name=self.name,
            category=self.category,
            account_id=account_id,
            points=self.points,
            timestamp=timestamp,
            message=message,
            evidence_txn_ids=sorted(evidence_txn_ids or []),
            evidence_accounts=sorted(evidence_accounts or []),
            details=details or {},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "category": self.category,
            "points": self.points,
            "description": self.description,
            "requires_graph": self.requires_graph,
        }
