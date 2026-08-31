"""The rule set, in the order the brief lists it."""

from __future__ import annotations

from .rules.base import Rule
from .rules.graph_rules import G1HighRiskProximity, G2SharedIdentifiers, G3EmergingRing
from .rules.mule import M1RapidFundMovement, M2MultipleSourceAccounts, M3CircularTransactions
from .rules.scam import (
    S1NewBeneficiaryHighValue,
    S2SuddenBehaviouralChange,
    S3VulnerableCustomerPattern,
)
from .rules.takeover import A1DeviceChangeAndTransfer, A2FailedLoginsThenSuccess

#: Every rule, instantiated once.
#:
#: CLAUDE.md section 4 says "implement all ten" and then lists eleven -- three
#: mule, three scam, two takeover, three graph. All eleven are implemented; the
#: count in the prose is the typo, not the list.
ALL_RULES: tuple[Rule, ...] = (
    M1RapidFundMovement(),
    M2MultipleSourceAccounts(),
    M3CircularTransactions(),
    S1NewBeneficiaryHighValue(),
    S2SuddenBehaviouralChange(),
    S3VulnerableCustomerPattern(),
    A1DeviceChangeAndTransfer(),
    A2FailedLoginsThenSuccess(),
    G1HighRiskProximity(),
    G2SharedIdentifiers(),
    G3EmergingRing(),
)

RULES_BY_ID: dict[str, Rule] = {rule.rule_id: rule for rule in ALL_RULES}


def rules_for(*, graph_enabled: bool = True) -> tuple[Rule, ...]:
    """The active rule set.

    With ``graph_enabled=False`` the network rules drop out, leaving exactly
    what a conventional per-transaction monitoring system can express. That is
    the "rules-only view" the brief calls the most persuasive element of the
    demo -- and it is a real re-run of the engine with a smaller rule set, not
    a cosmetic filter over the same results.
    """
    if graph_enabled:
        return ALL_RULES
    return tuple(rule for rule in ALL_RULES if not rule.requires_graph)
