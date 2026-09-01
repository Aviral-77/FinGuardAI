"""The presenter-driven demo scenario, split into a baseline and two beats.

The DEMO-SPEC demo is API-driven: nothing is flagged until the presenter fires
a trigger. So the world is partitioned:

* **baseline** -- what exists at Beat 0. Background accounts and their ambient
  traffic, plus the victim's benign history (so he has a low average transfer
  value and reads as elderly). Crucially it contains *none* of the
  ring-forming transactions, so at Beat 0 no rule fires and nothing is flagged.

* **Beat 1** -- the victim's transfers. Two high-value transfers to standing
  payees and the first, largest transfer to a brand-new beneficiary (Account
  A). Together these fire S3 + S1 and land the victim at 35 -- Enhanced
  monitoring, *not* a freeze. The demo's most important beat: one unusual
  customer, no mule pattern yet.

* **Beat 2** -- the fan-out. The funnel of unrelated senders into Account A, the
  rapid push-out, the ring cycle, the shared device, the proximity to a
  watchlisted account. Injected together, these carry the mule to 65 and the
  ring hub across 86.

Everything is drawn from the same deterministic generator that produces the
committed dataset (:func:`app.generator.generate.build_world`), split by the
transaction tags it already assigns. So the live demo and the batch dataset
tell the identical story from the identical numbers -- there is no second,
hand-tuned copy to drift.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..generator import typologies as T
from ..generator.generate import build_world
from ..models import Account, Beneficiary, Dataset, DeviceSession, Transaction

# Which transaction tags belong to which phase.
_BASELINE_TAGS = {"", "victim-history"}
_BEAT1_TAGS = {"scam-s3", "scam-s1"}
_BEAT2_TAGS = {
    "funnel-in",
    "mule-out",
    "ring-collect",
    "ring-out",
    "ring-cycle",
    "ring-roundtrip",
    "watchlist-link",
    "proximity-link",
}
# Tags excluded from the three-beat demo entirely: the stealth ring needs the
# ML layer (which the stage demo runs without), and the account-takeover is a
# separate scenario with its own preset.
_EXCLUDED_TAGS = {
    "ato-history",
    "ato-drain",
    "stealth-in",
    "stealth-hop",
    "stealth-chord",
}

#: Account A -- the mule the victim is tricked into funding.
ACCOUNT_A = T.PRIMARY_MULE

#: The mule accounts that share a device fingerprint (feeds G2). Their outbound
#: transfers in Beat 2 carry this as their ``device_id``, which is how the
#: shared-identifier link is established live rather than pre-seeded.
_SHARED_DEVICE_ACCOUNTS = set(T.MULES)


@dataclass(frozen=True)
class BeatTransaction:
    """One transaction the presenter fires, with its scripted timestamp."""

    from_account: str
    to_account: str
    amount: float
    channel: str
    timestamp: dt.datetime
    device_id: str | None = None
    tag: str = ""

    def to_payload(self) -> dict:
        payload: dict = {
            "from_account": self.from_account,
            "to_account": self.to_account,
            "amount": self.amount,
            "channel": self.channel,
            "timestamp": self.timestamp.isoformat(),
            "tag": self.tag,
        }
        if self.device_id:
            payload["device_id"] = self.device_id
        return payload


def _device_for(txn: Transaction) -> str | None:
    if txn.from_account in _SHARED_DEVICE_ACCOUNTS:
        return T.SHARED_MULE_DEVICE
    return None


def _split() -> tuple[Dataset, list[BeatTransaction], list[BeatTransaction]]:
    world, _ = build_world()

    baseline_txns: list[Transaction] = []
    beat1: list[BeatTransaction] = []
    beat2: list[BeatTransaction] = []

    for txn in world.transactions:
        if txn.tag in _EXCLUDED_TAGS:
            continue
        if txn.tag in _BASELINE_TAGS:
            baseline_txns.append(txn)
        elif txn.tag in _BEAT1_TAGS:
            beat1.append(_as_beat(txn))
        elif txn.tag in _BEAT2_TAGS:
            beat2.append(_as_beat(txn, device_id=_device_for(txn)))

    # Baseline device sessions: background devices only. The shared mule device,
    # the takeover devices and the stealth devices are kept out, so Beat 0 shows
    # no shared-identifier link. The mule device re-enters via Beat 2 payloads.
    baseline_sessions = [
        s for s in world.device_sessions if s.device_fingerprint.startswith("DFP-BG-")
    ]

    # Baseline beneficiaries: everything except the takeover pair (a separate
    # scenario). The victim -> Account A payee *is* kept, with its scripted
    # add-timestamp ~20h before the Beat-1 transfer: at Beat 0 a payee with no
    # payment to it flags nothing, and keeping it makes S1/S3 read "added 20h
    # earlier" rather than the "0h" an at-transfer auto-registration would give.
    excluded_adds = {(T.ATO_VICTIM, T.ATO_DESTINATION)}
    baseline_beneficiaries = [
        b for b in world.beneficiaries if (b.account, b.payee) not in excluded_adds
    ]

    baseline = Dataset(
        accounts=list(world.accounts),
        transactions=sorted(baseline_txns, key=lambda t: (t.timestamp, t.txn_id)),
        device_sessions=baseline_sessions,
        beneficiaries=baseline_beneficiaries,
    )
    beat1.sort(key=lambda b: b.timestamp)
    beat2.sort(key=lambda b: b.timestamp)
    return baseline, beat1, beat2


def _as_beat(txn: Transaction, device_id: str | None = None) -> BeatTransaction:
    return BeatTransaction(
        from_account=txn.from_account,
        to_account=txn.to_account,
        amount=txn.amount,
        channel=txn.channel,
        timestamp=txn.timestamp,
        device_id=device_id,
        tag=txn.tag,
    )


# Built once at import; the split is pure and deterministic.
_BASELINE, _BEAT1, _BEAT2 = _split()


def baseline_dataset() -> Dataset:
    """A fresh copy of the Beat-0 world (nothing flagged).

    Returns a deep-ish copy so the live state can mutate its lists without
    corrupting the template every reset.
    """
    return Dataset(
        accounts=list(_BASELINE.accounts),
        transactions=list(_BASELINE.transactions),
        device_sessions=list(_BASELINE.device_sessions),
        beneficiaries=list(_BASELINE.beneficiaries),
    )


def beat_one() -> list[BeatTransaction]:
    """The victim's transfers (fires S3 + S1 -> victim at 35)."""
    return list(_BEAT1)


def beat_two() -> list[BeatTransaction]:
    """The fan-out (carries the ring hub across 86)."""
    return list(_BEAT2)


def blocked_attempt() -> BeatTransaction:
    """A transfer into Account A, for the post-freeze 'it bounces' beat."""
    latest = max((b.timestamp for b in _BEAT2), default=_BASELINE.transactions[-1].timestamp)
    return BeatTransaction(
        from_account=T.FUNNEL_SENDERS[0],
        to_account=ACCOUNT_A,
        amount=90_000.0,
        channel="IMPS",
        timestamp=latest + dt.timedelta(hours=1),
        tag="blocked-attempt",
    )


def demo_accounts() -> set[str]:
    """Accounts that take part in the scripted ring, for UI labelling."""
    ids = {T.VICTIM, *T.MULES, *T.RING, *T.FUNNEL_SENDERS, *T.VICTIM_PAYEES, T.BRIDGE, T.WATCHLIST}
    ids.update(T.EXITS)
    return ids


__all__ = [
    "ACCOUNT_A",
    "BeatTransaction",
    "baseline_dataset",
    "beat_one",
    "beat_two",
    "blocked_attempt",
    "demo_accounts",
]
