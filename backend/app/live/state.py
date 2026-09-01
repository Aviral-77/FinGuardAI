"""Mutable, API-driven scoring state for the presenter demo.

Where the batch/replay path analyses a fixed dataset once, this holds a *living*
world that the presenter grows one transaction at a time. Each injected transfer
is appended and the rule engine is re-run over the accumulated state, so scores
climb as the ring assembles -- which is the whole point of the API-driven demo.

Re-running the whole engine per transaction (rather than an incremental update)
is a deliberate choice: the dataset is small, a run is a few milliseconds, and
reusing the exact same engine that the tests pin means the live scores are
identical to the batch scores by construction. There is no second scoring path
to keep in sync.

The anomaly layer is forced off here -- the stage story is rules-only.
"""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import dataclass, field

from ..analysis import Analysis, run_analysis
from ..copilot.templates import build_case
from ..engine.actions import action_for_account
from ..models import Account, Beneficiary, Dataset, DeviceSession, Transaction
from . import scenario


class FrozenAccountError(Exception):
    """Raised when a transaction touches a frozen account."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"Account {account_id} is frozen")


@dataclass
class InjectResult:
    transaction_id: str
    accepted: bool
    from_account: str
    to_account: str
    amount: float
    timestamp: str
    #: Accounts whose score changed, with their new score/band -- the payload
    #: the presenter (and the UI) watch climb.
    scores_updated: list[dict] = field(default_factory=list)


class LiveState:
    """One in-memory demo session.

    Guarded by a lock so the staggered batch endpoint and ad-hoc single
    transactions cannot interleave a half-applied mutation.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._dataset: Dataset
        self._frozen: set[str] = set()
        self._filed: set[str] = set()
        self._touched: set[str] = set()
        self._txn_seq = 0
        self._session_seq = 0
        self._analysis: Analysis
        self.reset()

    # -- lifecycle ---------------------------------------------------------

    def reset(self) -> None:
        """Back to Beat 0: baseline world, nothing frozen, nothing flagged."""
        with self._lock:
            self._dataset = scenario.baseline_dataset()
            self._frozen = set()
            self._filed = set()
            self._touched = set()
            self._txn_seq = len(self._dataset.transactions)
            self._session_seq = len(self._dataset.device_sessions)
            self._recompute()

    def _recompute(self) -> None:
        # ML off: the live stage demo is rules-only by design.
        self._analysis = run_analysis(self._dataset, ml_enabled=False)

    # -- mutation ----------------------------------------------------------

    def inject(
        self,
        from_account: str,
        to_account: str,
        amount: float,
        channel: str = "IMPS",
        timestamp: dt.datetime | None = None,
        device_id: str | None = None,
    ) -> InjectResult:
        """Apply one transaction and re-score. Raises if an endpoint is frozen.

        A freeze that did not actually stop money would be cosmetic; the brief
        insists it is real, so a transfer touching a frozen account is refused
        here, before any state changes.
        """
        with self._lock:
            if from_account in self._frozen:
                raise FrozenAccountError(from_account)
            if to_account in self._frozen:
                raise FrozenAccountError(to_account)

            when = timestamp or self._next_timestamp()
            self._txn_seq += 1
            txn = Transaction(
                txn_id=f"LIVE{self._txn_seq:06d}",
                from_account=from_account,
                to_account=to_account,
                amount=round(float(amount), 2),
                timestamp=when,
                channel=channel,
                tag="live",
            )

            self._ensure_account(from_account, when)
            self._ensure_account(to_account, when)
            self._register_new_beneficiary(from_account, to_account, when)
            if device_id:
                self._add_session(from_account, device_id, when)

            self._dataset.transactions.append(txn)
            self._touched.update((from_account, to_account))

            before = {a: s.score for a, s in self._analysis.scores.items()}
            self._recompute()

            updated = self._changed_scores(before, {from_account, to_account})
            return InjectResult(
                transaction_id=txn.txn_id,
                accepted=True,
                from_account=from_account,
                to_account=to_account,
                amount=txn.amount,
                timestamp=when.isoformat(),
                scores_updated=updated,
            )

    def freeze(self, account_id: str) -> dict:
        with self._lock:
            self._frozen.add(account_id)
            return self.account_view(account_id)

    def file_report(self, account_id: str) -> dict:
        with self._lock:
            self._filed.add(account_id)
            return self.account_view(account_id)

    # -- helpers -----------------------------------------------------------

    def _next_timestamp(self) -> dt.datetime:
        latest = max((t.timestamp for t in self._dataset.transactions), default=dt.datetime.min)
        return latest + dt.timedelta(minutes=1)

    def _ensure_account(self, account_id: str, when: dt.datetime) -> None:
        """Create a bare account on first sight, so ad-hoc IDs still work.

        The scripted demo only touches accounts that already exist, but the
        endpoint accepts arbitrary IDs (a presenter improvising), and a
        transaction to an unknown account should create it rather than error.
        """
        if any(a.account_id == account_id for a in self._dataset.accounts):
            return
        self._dataset.accounts.append(
            Account(
                account_id=account_id,
                name=account_id,
                open_date=(when - dt.timedelta(days=365)).date(),
                dormancy_flag=False,
                age_band="26-40",
                phone=f"+91-90000{len(self._dataset.accounts):05d}",
                address=f"{account_id} address",
                kyc_date=(when - dt.timedelta(days=350)).date(),
            )
        )

    def _register_new_beneficiary(self, account_id: str, payee: str, when: dt.datetime) -> None:
        """Treat a first-ever payment to a payee as adding a beneficiary now.

        S1 and S3 key on a *newly added* beneficiary. In the live model there is
        no separate 'add payee' event, so the first transfer to a counterparty
        the account has never paid registers the beneficiary at that moment --
        which is exactly the real-world signal (a new payee, then money).
        """
        already = any(
            b.account == account_id and b.payee == payee for b in self._dataset.beneficiaries
        )
        paid_before = any(
            t.from_account == account_id and t.to_account == payee
            for t in self._dataset.transactions
        )
        if already or paid_before:
            return
        self._dataset.beneficiaries.append(
            Beneficiary(account=account_id, payee=payee, added_timestamp=when - dt.timedelta(minutes=1))
        )

    def _add_session(self, account_id: str, device_id: str, when: dt.datetime) -> None:
        self._session_seq += 1
        self._dataset.device_sessions.append(
            DeviceSession(
                session_id=f"LIVES{self._session_seq:06d}",
                account=account_id,
                device_fingerprint=device_id,
                ip="203.0.113.44",
                login_result="success",
                timestamp=when - dt.timedelta(minutes=2),
                password_reset_flag=False,
            )
        )

    def _changed_scores(self, before: dict[str, int], forced: set[str]) -> list[dict]:
        rows: list[dict] = []
        for account_id, score in sorted(self._analysis.scores.items()):
            if score.band_code == "ALLOW" and account_id not in forced:
                continue
            if before.get(account_id) == score.score and account_id not in forced:
                continue
            rows.append(self._node_summary(account_id))
        return rows

    def _node_summary(self, account_id: str) -> dict:
        score = self._analysis.scores.get(account_id)
        account = self._analysis.ctx.accounts.get(account_id)
        return {
            "account_id": account_id,
            "score": score.score if score else 0,
            "band_code": score.band_code if score else "ALLOW",
            "band_label": score.band_label if score else "Allow transaction",
            "rule_ids": score.rule_ids if score else [],
            "frozen": account_id in self._frozen,
            "role": account.role if account else "background",
            "known_suspicious": account.known_suspicious if account else False,
        }

    # -- reads -------------------------------------------------------------

    @property
    def analysis(self) -> Analysis:
        return self._analysis

    @property
    def frozen(self) -> set[str]:
        return set(self._frozen)

    def is_frozen(self, account_id: str) -> bool:
        return account_id in self._frozen

    def ring(self) -> dict | None:
        """The detected ring: the G3 cluster, once it exists.

        Returns the member accounts and the total value moving among them, for
        the "MULE RING DETECTED · N accounts · ₹X in motion" banner.
        """
        members = sorted({h.account_id for h in self._analysis.hits if h.rule_id == "G3"})
        if len(members) < 3:
            return None
        member_set = set(members)
        value = sum(
            t.amount
            for t in self._dataset.transactions
            if t.from_account in member_set and t.to_account in member_set
        )
        return {
            "accounts": members,
            "count": len(members),
            "value_in_motion": round(value, 2),
        }

    def account_view(self, account_id: str) -> dict:
        """Live score, rules, narrative and recommended action for one account."""
        with self._lock:
            case = build_case(self._analysis, account_id)
            score = self._analysis.scores.get(account_id)
            action = action_for_account(score) if score else None
            case["frozen"] = account_id in self._frozen
            case["reported"] = account_id in self._filed
            # Beat 1 must read as "monitor only, insufficient evidence" -- the
            # spec's most important line. Below the step-up band there is no
            # blocking action, so we say so explicitly.
            case["actionable"] = bool(action and action.blocking)
            if not case["actionable"]:
                case["evidence_note"] = "Insufficient evidence for action. Watching for onward movement."
            return case

    def snapshot(self) -> dict:
        """Everything the canvas needs to render the current state."""
        with self._lock:
            nodes = []
            for account in self._dataset.accounts:
                if account.account_id not in self._touched and not self._has_traffic(account.account_id):
                    continue
                nodes.append(self._node_summary(account.account_id))
            edges = self._edges()
            return {
                "nodes": nodes,
                "edges": edges,
                "frozen": sorted(self._frozen),
                "ring": self.ring(),
                "flagged": sorted(self.analysis.flagged_accounts),
                "monitored_accounts": len(self._dataset.accounts),
                "transactions": len(self._dataset.transactions),
            }

    def _has_traffic(self, account_id: str) -> bool:
        return account_id in self._analysis.ctx.neighbours

    def _edges(self) -> list[dict]:
        graph = self._analysis.ctx.graph
        edges = []
        for source, target, data in graph.edges(data=True):
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "count": data["count"],
                    "total_amount": data["total_amount"],
                }
            )
        return edges


#: The process-wide demo session. One presenter, one screen, one state.
LIVE = LiveState()
