"""Account-takeover rules: A1, A2 (CLAUDE.md section 4)."""

from __future__ import annotations

import datetime as dt

from ...models import RuleHit
from ..context import EvaluationContext
from .base import Rule


class A1DeviceChangeAndTransfer(Rule):
    rule_id = "A1"
    name = "Device change + transfer"
    category = "takeover"
    points = 30
    description = (
        "A login from a new device, a password reset within 24 hours, and an "
        "outbound transfer after both."
    )

    window = dt.timedelta(hours=24)

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        """All three legs, in order, inside one 24-hour window.

        Each leg on its own is unremarkable -- people buy phones and forget
        passwords. The rule is the *sequence*.
        """
        hits: list[RuleHit] = []
        for account_id in sorted(ctx.sessions):
            sessions = ctx.sessions[account_id]
            debits = ctx.outgoing.get(account_id, ())
            if not debits:
                continue
            for session in sessions:
                if session.login_result != "success":
                    continue
                known = ctx.known_devices_before(account_id, session.timestamp)
                if not known or session.device_fingerprint in known:
                    continue  # not a new device
                reset = next(
                    (
                        s
                        for s in sessions
                        if s.password_reset_flag
                        and session.timestamp <= s.timestamp <= session.timestamp + self.window
                    ),
                    None,
                )
                if reset is None:
                    continue
                transfer = next(
                    (
                        t
                        for t in debits
                        if reset.timestamp <= t.timestamp <= session.timestamp + self.window
                    ),
                    None,
                )
                if transfer is None:
                    continue
                hits.append(
                    self.hit(
                        account_id,
                        transfer.timestamp,
                        (
                            f"New device {session.device_fingerprint} signed in, password "
                            f"reset {(reset.timestamp - session.timestamp).total_seconds() / 60:.0f} "
                            f"minutes later, then {transfer.amount:,.0f} sent out."
                        ),
                        evidence_txn_ids=[transfer.txn_id],
                        details={
                            "device_fingerprint": session.device_fingerprint,
                            "ip": session.ip,
                            "login_at": session.timestamp.isoformat(),
                            "password_reset_at": reset.timestamp.isoformat(),
                            "amount": transfer.amount,
                        },
                    )
                )
                break
        return hits


class A2FailedLoginsThenSuccess(Rule):
    rule_id = "A2"
    name = "Failed logins"
    category = "takeover"
    points = 20
    description = (
        "Five failed logins followed by a successful login from a different IP "
        "or device."
    )

    min_failures = 5
    window = dt.timedelta(hours=6)

    def evaluate(self, ctx: EvaluationContext) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for account_id in sorted(ctx.sessions):
            sessions = ctx.sessions[account_id]
            failures: list = []
            for session in sessions:
                if session.login_result == "failure":
                    failures.append(session)
                    continue
                recent = [
                    f for f in failures if session.timestamp - f.timestamp <= self.window
                ]
                if len(recent) < self.min_failures:
                    continue
                # The success must come from somewhere other than where the
                # customer normally signs in -- otherwise this is just someone
                # mistyping their own password.
                known = ctx.known_devices_before(account_id, recent[0].timestamp)
                changed = session.device_fingerprint not in known or session.ip not in {
                    s.ip for s in sessions if s.timestamp < recent[0].timestamp
                }
                if not changed:
                    continue
                hits.append(
                    self.hit(
                        account_id,
                        session.timestamp,
                        (
                            f"{len(recent)} failed logins, then a success from "
                            f"{session.ip} on device {session.device_fingerprint}."
                        ),
                        details={
                            "failed_attempts": len(recent),
                            "ip": session.ip,
                            "device_fingerprint": session.device_fingerprint,
                            "first_failure_at": recent[0].timestamp.isoformat(),
                        },
                    )
                )
                break
        return hits
