"""Pre-computed indexes every rule reads from.

Built once per analysis. Rules do lookups, never scans, so adding a rule costs
one pass over an account's own history rather than a pass over the dataset.

Determinism notes
-----------------
* Every index is a list sorted by ``(timestamp, id)`` -- never a set, and never
  raw dict iteration order.
* There is no notion of wall-clock "now". Where a rule needs a current time it
  uses :attr:`EvaluationContext.as_of`, which is the dataset's last timestamp.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx

from ..graphlayer.build import build_graph, undirected
from ..models import Account, Beneficiary, DeviceSession, Dataset, Transaction


@dataclass(slots=True)
class BalanceEvent:
    """One credit, with the running balance it produced.

    M1 ("rapid fund movement") is defined against a balance, but the brief's
    transaction table carries no balance column, so balance is reconstructed as
    the running sum of credits minus debits, floored at zero.
    """

    timestamp: dt.datetime
    txn_id: str
    amount: float
    balance_after: float


@dataclass
class EvaluationContext:
    dataset: Dataset

    accounts: dict[str, Account] = field(default_factory=dict)
    transactions: list[Transaction] = field(default_factory=list)

    #: account -> its transactions, sorted by time
    outgoing: dict[str, list[Transaction]] = field(default_factory=dict)
    incoming: dict[str, list[Transaction]] = field(default_factory=dict)

    #: account -> device sessions, sorted by time
    sessions: dict[str, list[DeviceSession]] = field(default_factory=dict)
    #: account -> beneficiaries, sorted by when they were added
    beneficiaries: dict[str, list[Beneficiary]] = field(default_factory=dict)

    #: account -> credits with running balance, sorted by time
    credits: dict[str, list[BalanceEvent]] = field(default_factory=dict)

    #: identifier value -> accounts sharing it (device fingerprint / phone / address)
    device_owners: dict[str, list[str]] = field(default_factory=dict)
    phone_owners: dict[str, list[str]] = field(default_factory=dict)
    address_owners: dict[str, list[str]] = field(default_factory=dict)

    #: undirected adjacency, for the graph rules
    neighbours: dict[str, list[str]] = field(default_factory=dict)

    #: the account-to-account graph, and its undirected projection
    graph: "nx.DiGraph" = field(default=None)  # type: ignore[assignment]
    ugraph: "nx.Graph" = field(default=None)  # type: ignore[assignment]

    as_of: dt.datetime = dt.datetime.min
    #: First timestamp in the dataset. Rules that ask "is this new?" measure
    #: against the observable window, not against the beginning of time.
    window_start: dt.datetime = dt.datetime.min

    # -- derived per-account statistics ------------------------------------

    def average_transfer(self, account_id: str) -> float:
        """Mean outbound transfer value. 0.0 when the account has never sent."""
        sent = self.outgoing.get(account_id, ())
        if not sent:
            return 0.0
        return statistics.fmean(t.amount for t in sent)

    def average_transfer_before(self, account_id: str, when: dt.datetime) -> float:
        """Mean outbound value *prior to* ``when``.

        Rules that compare a transfer against "the customer's average" must use
        the average as it stood before that transfer, or the transfer inflates
        the very baseline it is being judged against.
        """
        prior = [t.amount for t in self.outgoing.get(account_id, ()) if t.timestamp < when]
        return statistics.fmean(prior) if prior else 0.0

    def session_at(self, account_id: str, when: dt.datetime) -> DeviceSession | None:
        """The most recent successful login at or before ``when``.

        The transactions table has no device column, so a transfer is attributed
        to whichever session the customer was last authenticated on. That is the
        same assumption a real channel log would let you make, and it is what
        makes S2 and A1 evaluable at all.
        """
        best: DeviceSession | None = None
        for session in self.sessions.get(account_id, ()):
            if session.timestamp > when:
                break
            if session.login_result == "success":
                best = session
        return best

    def known_devices_before(self, account_id: str, when: dt.datetime) -> set[str]:
        return {
            s.device_fingerprint
            for s in self.sessions.get(account_id, ())
            if s.timestamp < when and s.login_result == "success"
        }

    def device_first_seen(self, account_id: str, fingerprint: str) -> dt.datetime | None:
        """When this account first authenticated successfully on this device."""
        for session in self.sessions.get(account_id, ()):
            if session.device_fingerprint == fingerprint and session.login_result == "success":
                return session.timestamp
        return None

    def device_is_unfamiliar(
        self, account_id: str, fingerprint: str, when: dt.datetime, *, settling: dt.timedelta
    ) -> bool:
        """Whether a device was still new to this account at ``when``.

        Asking "was this device in the known set just before this session"
        cannot work for a takeover: the attacker's own first login registers
        the device, so by the time they move money it already looks familiar.
        What actually distinguishes a takeover is that the device appeared
        moments ago against a long history on other devices -- so familiarity
        is measured from the device's *first* appearance, and the account must
        have a real history to be unfamiliar against.
        """
        first = self.device_first_seen(account_id, fingerprint)
        if first is None:
            return False
        prior = self.known_devices_before(account_id, first)
        if not prior:
            return False  # no established baseline to be a departure from
        return when - first <= settling


def build_context(dataset: Dataset) -> EvaluationContext:
    """Index a dataset for rule evaluation."""
    ctx = EvaluationContext(dataset=dataset)
    ctx.accounts = {a.account_id: a for a in dataset.accounts}

    ctx.transactions = sorted(dataset.transactions, key=lambda t: (t.timestamp, t.txn_id))

    outgoing: dict[str, list[Transaction]] = defaultdict(list)
    incoming: dict[str, list[Transaction]] = defaultdict(list)
    neighbours: dict[str, set[str]] = defaultdict(set)
    for txn in ctx.transactions:
        outgoing[txn.from_account].append(txn)
        incoming[txn.to_account].append(txn)
        neighbours[txn.from_account].add(txn.to_account)
        neighbours[txn.to_account].add(txn.from_account)
    ctx.outgoing = dict(outgoing)
    ctx.incoming = dict(incoming)
    ctx.neighbours = {k: sorted(v) for k, v in sorted(neighbours.items())}

    sessions: dict[str, list[DeviceSession]] = defaultdict(list)
    for session in sorted(dataset.device_sessions, key=lambda s: (s.timestamp, s.session_id)):
        sessions[session.account].append(session)
    ctx.sessions = dict(sessions)

    beneficiaries: dict[str, list[Beneficiary]] = defaultdict(list)
    for beneficiary in sorted(
        dataset.beneficiaries, key=lambda b: (b.added_timestamp, b.account, b.payee)
    ):
        beneficiaries[beneficiary.account].append(beneficiary)
    ctx.beneficiaries = dict(beneficiaries)

    # -- running balances --------------------------------------------------
    movements: dict[str, list[tuple[dt.datetime, str, float, str]]] = defaultdict(list)
    for txn in ctx.transactions:
        movements[txn.to_account].append((txn.timestamp, txn.txn_id, txn.amount, "credit"))
        movements[txn.from_account].append((txn.timestamp, txn.txn_id, -txn.amount, "debit"))
    credits: dict[str, list[BalanceEvent]] = {}
    for account_id in sorted(movements):
        balance = 0.0
        events: list[BalanceEvent] = []
        for timestamp, txn_id, delta, kind in sorted(movements[account_id]):
            balance = max(0.0, balance + delta)
            if kind == "credit":
                events.append(BalanceEvent(timestamp, txn_id, delta, balance))
        credits[account_id] = events
    ctx.credits = credits

    # -- shared identifiers (G2) ------------------------------------------
    device_owners: dict[str, set[str]] = defaultdict(set)
    for session in dataset.device_sessions:
        device_owners[session.device_fingerprint].add(session.account)
    ctx.device_owners = {k: sorted(v) for k, v in sorted(device_owners.items())}

    phone_owners: dict[str, set[str]] = defaultdict(set)
    address_owners: dict[str, set[str]] = defaultdict(set)
    for account in dataset.accounts:
        phone_owners[account.phone].add(account.account_id)
        address_owners[account.address].add(account.account_id)
    ctx.phone_owners = {k: sorted(v) for k, v in sorted(phone_owners.items())}
    ctx.address_owners = {k: sorted(v) for k, v in sorted(address_owners.items())}

    ctx.graph = build_graph(dataset)
    ctx.ugraph = undirected(ctx.graph)

    ctx.as_of = ctx.transactions[-1].timestamp if ctx.transactions else dt.datetime.min
    ctx.window_start = ctx.transactions[0].timestamp if ctx.transactions else dt.datetime.min
    return ctx
