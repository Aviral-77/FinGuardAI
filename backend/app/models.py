"""Domain records shared by the generator, the engine and the API.

Plain dataclasses rather than Pydantic models: these are hot in the rule engine
(hundreds of thousands of attribute reads during a replay) and FastAPI
serialises dataclasses natively, so there is nothing to gain from validation on
every construction.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# The four generated tables (CLAUDE.md section 5)
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Account:
    account_id: str
    name: str
    open_date: dt.date
    dormancy_flag: bool
    age_band: str  # "18-25" | "26-40" | "41-60" | "60+"
    phone: str
    address: str
    kyc_date: dt.date
    #: Flagged by a *prior* investigation. This is the only input rule G1
    #: ("high-risk proximity") treats as ground truth -- it is a watchlist, not
    #: something the engine infers from its own scores, which would make G1
    #: self-referential and its output unauditable.
    known_suspicious: bool = False
    #: Narrative role, used only for demo labelling and never read by a rule.
    role: str = "background"  # background | victim | mule | ring | stealth | ato

    @property
    def is_elderly(self) -> bool:
        return self.age_band == "60+"


@dataclass(slots=True)
class Transaction:
    txn_id: str
    from_account: str
    to_account: str
    amount: float
    timestamp: dt.datetime
    channel: str
    #: Narrative tag for the demo script; rules never read it.
    tag: str = ""


@dataclass(slots=True)
class DeviceSession:
    session_id: str
    account: str
    device_fingerprint: str
    ip: str
    login_result: str  # "success" | "failure"
    timestamp: dt.datetime
    password_reset_flag: bool


@dataclass(slots=True)
class Beneficiary:
    account: str
    payee: str
    added_timestamp: dt.datetime


@dataclass(slots=True)
class Dataset:
    accounts: list[Account]
    transactions: list[Transaction]
    device_sessions: list[DeviceSession]
    beneficiaries: list[Beneficiary]

    def account_map(self) -> dict[str, Account]:
        return {a.account_id: a for a in self.accounts}


# --------------------------------------------------------------------------
# Engine output
# --------------------------------------------------------------------------


@dataclass(slots=True)
class RuleHit:
    """One rule firing against one account.

    ``points`` is the brief's fixed value for the rule. Evidence is carried so
    the copilot can cite specific rows -- the audit chain the brief demands runs
    score -> rule -> these ids.
    """

    rule_id: str
    rule_name: str
    category: str
    account_id: str
    points: int
    timestamp: dt.datetime
    message: str
    evidence_txn_ids: list[str] = field(default_factory=list)
    evidence_accounts: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def key(self) -> tuple[str, str]:
        return (self.account_id, self.rule_id)


@dataclass(slots=True)
class AccountScore:
    account_id: str
    score: int
    band_code: str
    band_label: str
    hits: list[RuleHit] = field(default_factory=list)

    @property
    def rule_ids(self) -> list[str]:
        return sorted({h.rule_id for h in self.hits})


@dataclass(slots=True)
class MLFinding:
    """Anomaly-model output for one account.

    Deliberately separate from :class:`AccountScore`. The brief's non-negotiable
    is that every point in a score traces to a named rule, so the anomaly score
    lives in its own column and never adds points.
    """

    account_id: str
    anomaly_score: float  # 0..1, higher = more anomalous
    is_anomalous: bool
    #: Not flagged outright, but anomalous enough to join a cluster that
    #: flagged accounts have already seeded. See ``ML_ELEVATED_QUANTILE``.
    is_elevated: bool
    rank: int
    top_features: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class MLNetwork:
    """A cluster of anomalous accounts that forms a connected sub-graph."""

    network_id: str
    account_ids: list[str]
    density: float
    mean_anomaly: float
    max_rule_score: int
    missed_by_rules: bool
    action_code: str
    action_label: str
    rationale: list[str] = field(default_factory=list)
