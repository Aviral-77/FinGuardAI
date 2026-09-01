"""Deterministic case-narrative composer (DEMO-SPEC).

The dashboard and the PDF both show a plain-English paragraph explaining why an
account was flagged. Per DEMO-SPEC this is assembled from templates filled with
the real case values -- not written by a model. It renders instantly, cannot
fail live, and reads identically on every run. "If asked, this is generated
from the case facts -- which is exactly what it is."

Each fired rule contributes one clause, drawn from the rule's own evidence
(``RuleHit.details``). Clauses are ordered by the points the rule contributed,
highest first, so the paragraph leads with the strongest signal. It closes with
a fixed classification line chosen by the highest-scoring rule's category.

The optional LLM layer in :mod:`app.copilot.llm` rewrites *this* paragraph's
facts into prose when a provider is configured; with none, this is what ships.
"""

from __future__ import annotations

from ..models import RuleHit

# --------------------------------------------------------------------------
# Per-rule clauses
# --------------------------------------------------------------------------
#
# Each takes the rule's fired hit and returns a lower-case clause that slots
# into "Account X <clause>, <clause> and <clause>." The values come straight
# from the evidence the rule recorded, so the sentence is literally the case.


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def _clause_m1(h: RuleHit) -> str:
    d = h.details
    hours = d.get("hours_to_clear", 0)
    when = f"{hours:.0f} hours" if hours >= 1 else f"{hours * 60:.0f} minutes"
    return f"moved {_pct(d.get('share', 0))} of the incoming balance out within {when}"


def _clause_m2(h: RuleHit) -> str:
    d = h.details
    return (
        f"received funds from {d.get('unique_senders', 0)} unrelated accounts "
        f"in clustered amounts around ₹{d.get('mean_incoming', 0):,.0f}"
    )


def _clause_m3(h: RuleHit) -> str:
    d = h.details
    return (
        f"passed funds around a loop of {len(set(d.get('cycle', [])))} accounts "
        f"that returned to the origin within {d.get('hours', 0):.0f} hours"
    )


def _clause_s1(h: RuleHit) -> str:
    d = h.details
    return (
        f"made its first transfer to a beneficiary added "
        f"{d.get('hours_after_add', 0):.0f}h earlier at "
        f"{d.get('multiple', 0):.0f}× its usual value"
    )


def _clause_s2(h: RuleHit) -> str:
    d = h.details
    return (
        f"sent {d.get('multiple', 0):.0f}× its usual value from an unrecognised "
        f"device ({d.get('device_fingerprint', 'unknown')})"
    )


def _clause_s3(h: RuleHit) -> str:
    d = h.details
    return (
        f"made {d.get('high_value_transfers', 0)} high-value transfers after a "
        f"new payee was added within the previous 48 hours"
    )


def _clause_a1(h: RuleHit) -> str:
    return (
        "signed in from a new device, reset its password within the hour, and "
        "immediately moved funds out"
    )


def _clause_a2(h: RuleHit) -> str:
    d = h.details
    return (
        f"was accessed after {d.get('failed_attempts', 0)} failed logins, then a "
        f"success from an unfamiliar location"
    )


def _clause_g1(h: RuleHit) -> str:
    d = h.details
    return (
        f"sits within {d.get('hops', 2)} hops of {d.get('suspect', 'a')} account "
        f"flagged by a previous investigation"
    )


def _clause_g2(h: RuleHit) -> str:
    d = h.details
    shared = d.get("shared_with", [])
    kind = d.get("identifier_type", "identifier")
    return f"shares a {kind} with {len(shared)} other flagged account" + (
        "s" if len(shared) != 1 else ""
    )


def _clause_g3(h: RuleHit) -> str:
    d = h.details
    return (
        f"sits inside a cluster of {d.get('cluster_size', 0)} accounts moving "
        f"money on near-identical timing"
    )


_CLAUSES = {
    "M1": _clause_m1,
    "M2": _clause_m2,
    "M3": _clause_m3,
    "S1": _clause_s1,
    "S2": _clause_s2,
    "S3": _clause_s3,
    "A1": _clause_a1,
    "A2": _clause_a2,
    "G1": _clause_g1,
    "G2": _clause_g2,
    "G3": _clause_g3,
}

# --------------------------------------------------------------------------
# Closing classification line, chosen by the top-scoring category
# --------------------------------------------------------------------------

_CLASSIFICATION = {
    "mule": (
        "The pattern is consistent with a mule account layering the proceeds of "
        "a social-engineering scam."
    ),
    "scam": (
        "The pattern is consistent with a customer being defrauded through "
        "social engineering."
    ),
    "takeover": (
        "The pattern is consistent with an account takeover."
    ),
    "graph": (
        "The pattern is consistent with a coordinated mule network."
    ),
}

_VICTIM_CLASSIFICATION = (
    "This account is assessed as the victim of a scam rather than a participant "
    "in the network."
)


def _first_hit_per_rule(hits: list[RuleHit]) -> list[RuleHit]:
    """One hit per rule (the one that scored), highest points first.

    A rule scores once however often it fires, so the narrative cites each rule
    once, and ordering by points puts the strongest signal at the front of the
    sentence.
    """
    seen: set[str] = set()
    unique: list[RuleHit] = []
    for hit in sorted(hits, key=lambda h: (-h.points, h.timestamp, h.rule_id)):
        if hit.rule_id in seen:
            continue
        seen.add(hit.rule_id)
        unique.append(hit)
    return unique


def _join_clauses(clauses: list[str]) -> str:
    if len(clauses) == 1:
        return clauses[0]
    if len(clauses) == 2:
        return f"{clauses[0]} and {clauses[1]}"
    return ", ".join(clauses[:-1]) + f", and {clauses[-1]}"


def compose_narrative(account_id: str, hits: list[RuleHit], *, is_victim: bool = False) -> str:
    """The case paragraph for one account, from its fired rules.

    ``is_victim`` swaps the closing line: an elderly customer whose only high
    signals are scam indicators is the person defrauded, and the brief is
    emphatic that the product must not treat the victim as a suspect.
    """
    ranked = _first_hit_per_rule(hits)
    if not ranked:
        return (
            f"Account {account_id} triggered no detection rule. On the rule "
            f"engine it would be allowed through with no action."
        )

    clauses = [_CLAUSES[h.rule_id](h) for h in ranked if h.rule_id in _CLAUSES]
    body = _join_clauses(clauses)

    top_category = ranked[0].category
    if is_victim:
        closing = _VICTIM_CLASSIFICATION
    else:
        closing = _CLASSIFICATION.get(top_category, _CLASSIFICATION["graph"])

    return f"Account {account_id} {body}. {closing}"
