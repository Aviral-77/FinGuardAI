"""Scam-indicator rules: S1, S2, S3 (CLAUDE.md section 4)."""

from __future__ import annotations

import datetime as dt

from ...models import RuleHit
from ..context import EvaluationContext
from .base import Rule

#: A customer with almost no history has no meaningful "average transfer", and
#: dividing by it produces enormous multiples on ordinary payments. Rules that
#: compare against an average require at least this many prior transfers.
MIN_HISTORY = 3


class S1NewBeneficiaryHighValue(Rule):
    rule_id = "S1"
    name = "New beneficiary, high value"
    category = "scam"
    points = 20
    description = (
        "A beneficiary is added and the first transfer to them exceeds 5x the "
        "customer's average transfer value."
    )

    multiple = 5.0

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for account_id in sorted(ctx.beneficiaries):
            sent = ctx.outgoing.get(account_id, ())
            if len(sent) < MIN_HISTORY:
                continue
            for beneficiary in ctx.beneficiaries[account_id]:
                # "Newly added" means added inside the observable window. A
                # payee registered three years ago is a standing relationship,
                # and treating the customer's first *in-window* payment to them
                # as a first-ever payment turns every ordinary large transfer
                # into an alert.
                if beneficiary.added_timestamp < ctx.window_start:
                    continue
                first = next(
                    (
                        t
                        for t in sent
                        if t.to_account == beneficiary.payee
                        and t.timestamp >= beneficiary.added_timestamp
                    ),
                    None,
                )
                if first is None:
                    continue
                baseline = ctx.average_transfer_before(account_id, first.timestamp)
                if baseline <= 0 or first.amount <= baseline * self.multiple:
                    continue
                hits.append(
                    self.hit(
                        account_id,
                        first.timestamp,
                        (
                            f"First transfer to a payee added "
                            f"{(first.timestamp - beneficiary.added_timestamp).total_seconds() / 3600:.0f}h "
                            f"earlier was {first.amount:,.0f} against a "
                            f"{baseline:,.0f} average -- "
                            f"{first.amount / baseline:.0f}x."
                        ),
                        evidence_txn_ids=[first.txn_id],
                        evidence_accounts=[beneficiary.payee],
                        details={
                            "payee": beneficiary.payee,
                            "amount": first.amount,
                            "average_transfer": round(baseline, 2),
                            "multiple": round(first.amount / baseline, 1),
                            "hours_after_add": round(
                                (first.timestamp - beneficiary.added_timestamp).total_seconds()
                                / 3600,
                                1,
                            ),
                        },
                    )
                )
                break
        return hits


class S2SuddenBehaviouralChange(Rule):
    rule_id = "S2"
    name = "Sudden behavioural change"
    category = "scam"
    points = 25
    description = (
        "A transfer is made from an unfamiliar device or location and is worth "
        "more than 3x the customer's historical average."
    )

    multiple = 3.0
    #: How long a newly-seen device stays "unfamiliar". Beyond this the
    #: customer has plausibly just changed phones.
    settling = dt.timedelta(hours=48)

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for account_id in sorted(ctx.outgoing):
            sent = ctx.outgoing[account_id]
            if len(sent) < MIN_HISTORY:
                continue
            for txn in sent:
                baseline = ctx.average_transfer_before(account_id, txn.timestamp)
                if baseline <= 0 or txn.amount <= baseline * self.multiple:
                    continue
                session = ctx.session_at(account_id, txn.timestamp)
                if session is None:
                    continue
                if not ctx.device_is_unfamiliar(
                    account_id,
                    session.device_fingerprint,
                    txn.timestamp,
                    settling=self.settling,
                ):
                    continue
                hits.append(
                    self.hit(
                        account_id,
                        txn.timestamp,
                        (
                            f"{txn.amount:,.0f} sent from an unrecognised device "
                            f"({session.device_fingerprint}, {session.ip}) -- "
                            f"{txn.amount / baseline:.0f}x this customer's "
                            f"{baseline:,.0f} average."
                        ),
                        evidence_txn_ids=[txn.txn_id],
                        details={
                            "device_fingerprint": session.device_fingerprint,
                            "ip": session.ip,
                            "amount": txn.amount,
                            "average_transfer": round(baseline, 2),
                            "multiple": round(txn.amount / baseline, 1),
                        },
                    )
                )
                break
        return hits


class S3VulnerableCustomerPattern(Rule):
    rule_id = "S3"
    name = "Elderly / vulnerable pattern"
    category = "scam"
    points = 15
    description = (
        "An elderly or vulnerable customer makes multiple high-value transfers "
        "with a new payee added in the previous 48 hours."
    )

    lookback = dt.timedelta(hours=48)
    high_value_multiple = 3.0
    min_transfers = 2

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for account_id in sorted(ctx.outgoing):
            account = ctx.accounts.get(account_id)
            if account is None or not account.is_elderly:
                continue
            sent = ctx.outgoing[account_id]
            if len(sent) < MIN_HISTORY:
                continue
            added = ctx.beneficiaries.get(account_id, ())
            recent_high: list[str] = []
            for txn in sent:
                baseline = ctx.average_transfer_before(account_id, txn.timestamp)
                if baseline <= 0 or txn.amount <= baseline * self.high_value_multiple:
                    continue
                recent_high.append(txn.txn_id)
                if len(recent_high) < self.min_transfers:
                    continue
                new_payees = [
                    b
                    for b in added
                    if txn.timestamp - self.lookback <= b.added_timestamp <= txn.timestamp
                ]
                if not new_payees:
                    continue
                hits.append(
                    self.hit(
                        account_id,
                        txn.timestamp,
                        (
                            f"Vulnerable customer ({account.age_band}) made "
                            f"{len(recent_high)} high-value transfers after adding "
                            f"payee {new_payees[-1].payee} "
                            f"{(txn.timestamp - new_payees[-1].added_timestamp).total_seconds() / 3600:.0f}h "
                            f"earlier."
                        ),
                        evidence_txn_ids=recent_high,
                        evidence_accounts=[b.payee for b in new_payees],
                        details={
                            "age_band": account.age_band,
                            "high_value_transfers": len(recent_high),
                            "new_payees": [b.payee for b in new_payees],
                        },
                    )
                )
                break
        return hits
