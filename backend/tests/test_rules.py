"""Per-rule unit tests against hand-built fixtures.

Small, explicit worlds -- a handful of transactions each -- so a failure points
at one rule rather than at the dataset. The scenario tests cover the rules in
combination; these cover them in isolation, including the negative case, which
is where threshold bugs actually live.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.engine.context import build_context
from app.engine.registry import RULES_BY_ID
from app.engine.scoring import band_for, score_accounts
from app.models import Account, Beneficiary, Dataset, DeviceSession, Transaction

BASE = dt.datetime(2026, 5, 1, 9, 0, 0)


def account(account_id: str, *, age_band: str = "26-40", suspicious: bool = False, **kwargs):
    return Account(
        account_id=account_id,
        name=f"Holder {account_id}",
        open_date=dt.date(2020, 1, 1),
        dormancy_flag=False,
        age_band=age_band,
        phone=kwargs.get("phone", f"+91-9{account_id[-8:]:0>9}"),
        address=kwargs.get("address", f"{account_id} Street"),
        kyc_date=dt.date(2020, 2, 1),
        known_suspicious=suspicious,
    )


def txn(seq: int, src: str, dst: str, amount: float, offset_h: float) -> Transaction:
    return Transaction(
        txn_id=f"T{seq:04d}",
        from_account=src,
        to_account=dst,
        amount=amount,
        timestamp=BASE + dt.timedelta(hours=offset_h),
        channel="ACH",
    )


def session(seq: int, acct: str, device: str, ip: str, offset_h: float, *, result="success", reset=False):
    return DeviceSession(
        session_id=f"S{seq:04d}",
        account=acct,
        device_fingerprint=device,
        ip=ip,
        login_result=result,
        timestamp=BASE + dt.timedelta(hours=offset_h),
        password_reset_flag=reset,
    )


def world(accounts, transactions, sessions=(), beneficiaries=()):
    return build_context(
        Dataset(list(accounts), list(transactions), list(sessions), list(beneficiaries))
    )


def fire(rule_id: str, ctx):
    return RULES_BY_ID[rule_id].evaluate(ctx)


# --------------------------------------------------------------------------
# M1 -- rapid fund movement
# --------------------------------------------------------------------------


def test_m1_fires_when_most_of_the_balance_leaves_within_a_day():
    ctx = world(
        [account("A"), account("B"), account("C")],
        [txn(1, "B", "A", 100_000, 0), txn(2, "A", "C", 90_000, 6)],
    )
    hits = fire("M1", ctx)
    assert [h.account_id for h in hits] == ["A"]
    assert hits[0].details["share"] == pytest.approx(0.9)


def test_m1_ignores_a_slower_drain():
    """90% out, but after 30 hours -- outside the window."""
    ctx = world(
        [account("A"), account("B"), account("C")],
        [txn(1, "B", "A", 100_000, 0), txn(2, "A", "C", 90_000, 30)],
    )
    assert fire("M1", ctx) == []


def test_m1_ignores_a_partial_drain():
    ctx = world(
        [account("A"), account("B"), account("C")],
        [txn(1, "B", "A", 100_000, 0), txn(2, "A", "C", 70_000, 6)],
    )
    assert fire("M1", ctx) == []


def test_m1_does_not_count_a_later_credit_towards_an_earlier_drain():
    """The share of a balance that left cannot exceed 100%.

    Money arriving after the credit being judged must not inflate the outflow
    attributed to it.
    """
    ctx = world(
        [account("A"), account("B"), account("C")],
        [
            txn(1, "B", "A", 100_000, 0),
            txn(2, "B", "A", 500_000, 2),
            txn(3, "A", "C", 550_000, 4),
        ],
    )
    for hit in fire("M1", ctx):
        assert hit.details["share"] <= 1.0


# --------------------------------------------------------------------------
# M2 -- multiple source accounts
# --------------------------------------------------------------------------


def test_m2_fires_on_six_clustered_senders():
    senders = [f"S{i}" for i in range(6)]
    ctx = world(
        [account("A"), *[account(s) for s in senders]],
        [txn(i, s, "A", 100_000 + i * 500, i * 4) for i, s in enumerate(senders)],
    )
    hits = fire("M2", ctx)
    assert [h.account_id for h in hits] == ["A"]
    assert hits[0].details["unique_senders"] == 6


def test_m2_ignores_five_senders():
    senders = [f"S{i}" for i in range(5)]
    ctx = world(
        [account("A"), *[account(s) for s in senders]],
        [txn(i, s, "A", 100_000, i * 4) for i, s in enumerate(senders)],
    )
    assert fire("M2", ctx) == []


def test_m2_ignores_six_senders_with_scattered_amounts():
    """Count alone is not the rule -- the amounts have to cluster."""
    senders = [f"S{i}" for i in range(6)]
    amounts = [5_000, 40_000, 120_000, 260_000, 610_000, 1_400_000]
    ctx = world(
        [account("A"), *[account(s) for s in senders]],
        [txn(i, s, "A", amounts[i], i * 4) for i, s in enumerate(senders)],
    )
    assert fire("M2", ctx) == []


# --------------------------------------------------------------------------
# M3 -- circular transactions
# --------------------------------------------------------------------------


def test_m3_fires_on_a_three_account_loop_inside_72h():
    ctx = world(
        [account("A"), account("B"), account("C")],
        [
            txn(1, "A", "B", 90_000, 0),
            txn(2, "B", "C", 88_000, 10),
            txn(3, "C", "A", 86_000, 20),
        ],
    )
    assert sorted(h.account_id for h in fire("M3", ctx)) == ["A", "B", "C"]


def test_m3_ignores_a_loop_that_closes_too_late():
    ctx = world(
        [account("A"), account("B"), account("C")],
        [
            txn(1, "A", "B", 90_000, 0),
            txn(2, "B", "C", 88_000, 10),
            txn(3, "C", "A", 86_000, 100),
        ],
    )
    assert fire("M3", ctx) == []


# --------------------------------------------------------------------------
# S1 / S3 -- scam indicators
# --------------------------------------------------------------------------


def test_s1_fires_on_a_large_first_transfer_to_a_new_payee():
    ctx = world(
        [account("A"), account("P"), account("Q")],
        [
            txn(1, "A", "Q", 5_000, 0),
            txn(2, "A", "Q", 4_000, 24),
            txn(3, "A", "Q", 6_000, 48),
            txn(4, "A", "P", 90_000, 72),
        ],
        beneficiaries=[Beneficiary("A", "P", BASE + dt.timedelta(hours=70))],
    )
    hits = fire("S1", ctx)
    assert [h.account_id for h in hits] == ["A"]


def test_s1_ignores_a_long_standing_payee():
    """A payee registered before the window is not a new beneficiary."""
    ctx = world(
        [account("A"), account("P"), account("Q")],
        [
            txn(1, "A", "Q", 5_000, 0),
            txn(2, "A", "Q", 4_000, 24),
            txn(3, "A", "Q", 6_000, 48),
            txn(4, "A", "P", 90_000, 72),
        ],
        beneficiaries=[Beneficiary("A", "P", BASE - dt.timedelta(days=400))],
    )
    assert fire("S1", ctx) == []


def test_s3_requires_an_elderly_customer():
    transactions = [
        txn(1, "A", "Q", 5_000, 0),
        txn(2, "A", "Q", 4_000, 24),
        txn(3, "A", "Q", 6_000, 48),
        txn(4, "A", "Q", 60_000, 72),
        txn(5, "A", "Q", 70_000, 78),
    ]
    beneficiaries = [Beneficiary("A", "P", BASE + dt.timedelta(hours=60))]

    elderly = world(
        [account("A", age_band="60+"), account("P"), account("Q")], transactions, beneficiaries=beneficiaries
    )
    assert [h.account_id for h in fire("S3", elderly)] == ["A"]

    younger = world(
        [account("A", age_band="26-40"), account("P"), account("Q")], transactions, beneficiaries=beneficiaries
    )
    assert fire("S3", younger) == []


# --------------------------------------------------------------------------
# A1 / A2 -- account takeover
# --------------------------------------------------------------------------


def _ato_history():
    sessions = [session(i, "A", "DEV-HOME", "10.0.0.1", i * 24) for i in range(5)]
    transactions = [txn(i, "A", "B", 5_000, i * 24) for i in range(5)]
    return sessions, transactions


def test_a1_needs_all_three_legs():
    sessions, transactions = _ato_history()
    sessions += [
        session(90, "A", "DEV-NEW", "185.0.0.9", 200),
        session(91, "A", "DEV-NEW", "185.0.0.9", 201, reset=True),
    ]
    transactions.append(txn(90, "A", "B", 80_000, 202))
    assert [h.account_id for h in fire("A1", world([account("A"), account("B")], transactions, sessions))] == ["A"]


def test_a1_does_not_fire_without_a_password_reset():
    sessions, transactions = _ato_history()
    sessions.append(session(90, "A", "DEV-NEW", "185.0.0.9", 200))
    transactions.append(txn(90, "A", "B", 80_000, 202))
    assert fire("A1", world([account("A"), account("B")], transactions, sessions)) == []


def test_a2_fires_after_five_failures_then_a_success_elsewhere():
    sessions, transactions = _ato_history()
    sessions += [
        session(80 + i, "A", "DEV-NEW", "185.0.0.9", 200 + i * 0.1, result="failure")
        for i in range(5)
    ]
    sessions.append(session(90, "A", "DEV-NEW", "185.0.0.9", 201))
    assert [h.account_id for h in fire("A2", world([account("A"), account("B")], transactions, sessions))] == ["A"]


def test_a2_ignores_four_failures():
    sessions, transactions = _ato_history()
    sessions += [
        session(80 + i, "A", "DEV-NEW", "185.0.0.9", 200 + i * 0.1, result="failure")
        for i in range(4)
    ]
    sessions.append(session(90, "A", "DEV-NEW", "185.0.0.9", 201))
    assert fire("A2", world([account("A"), account("B")], transactions, sessions)) == []


# --------------------------------------------------------------------------
# G1 / G2 -- graph rules
# --------------------------------------------------------------------------


def test_g1_reaches_two_hops_but_not_three():
    ctx = world(
        [account("W", suspicious=True), account("B"), account("C"), account("D")],
        [txn(1, "B", "W", 10_000, 0), txn(2, "C", "B", 10_000, 1), txn(3, "D", "C", 10_000, 2)],
    )
    flagged = sorted(h.account_id for h in fire("G1", ctx))
    assert flagged == ["B", "C"]
    assert "D" not in flagged


def test_g2_fires_on_three_accounts_sharing_a_device():
    ctx = world(
        [account("A"), account("B"), account("C")],
        [txn(1, "A", "B", 1_000, 0)],
        sessions=[
            session(1, "A", "DEV-SHARED", "10.0.0.1", 0),
            session(2, "B", "DEV-SHARED", "10.0.0.1", 1),
            session(3, "C", "DEV-SHARED", "10.0.0.1", 2),
        ],
    )
    assert sorted(h.account_id for h in fire("G2", ctx)) == ["A", "B", "C"]


def test_g2_ignores_two_accounts_sharing_a_device():
    ctx = world(
        [account("A"), account("B")],
        [txn(1, "A", "B", 1_000, 0)],
        sessions=[
            session(1, "A", "DEV-SHARED", "10.0.0.1", 0),
            session(2, "B", "DEV-SHARED", "10.0.0.1", 1),
        ],
    )
    assert fire("G2", ctx) == []


# --------------------------------------------------------------------------
# Scoring and bands
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "Allow transaction"),
        (30, "Allow transaction"),
        (31, "Enhanced monitoring"),
        (50, "Enhanced monitoring"),
        (51, "Step-up authentication"),
        (70, "Step-up authentication"),
        (71, "Manual fraud review"),
        (85, "Manual fraud review"),
        (86, "Temporary block / freeze"),
        (100, "Temporary block / freeze"),
    ],
)
def test_score_bands_match_the_brief(score, expected):
    assert band_for(score).label == expected


def test_a_rule_scores_once_however_often_it_fires():
    """Otherwise the same behaviour would be worth more on a finer data slice."""
    rule = RULES_BY_ID["M1"]
    hits = [
        rule.hit("A", BASE, "first"),
        rule.hit("A", BASE + dt.timedelta(hours=1), "second"),
        rule.hit("A", BASE + dt.timedelta(hours=2), "third"),
    ]
    scored = score_accounts(hits)
    assert scored["A"].score == rule.points
    assert len(scored["A"].hits) == 3  # all three kept as evidence
