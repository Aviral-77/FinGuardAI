"""Builds the FinGuard AI world and writes the four tables to CSV.

Run with::

    python -m app.generator.generate

Determinism is the whole point (CLAUDE.md section 10: "the ring must form the
same way every run"). One seed drives Faker and ``random``; every collection is
sorted before it is written; no wall-clock time is ever read. Running this twice
produces byte-identical CSVs, and ``tests/test_determinism.py`` asserts it.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
from dataclasses import asdict

from faker import Faker

from ..config import (
    ACCOUNTS_CSV,
    BENEFICIARIES_CSV,
    DEVICE_SESSIONS_CSV,
    N_BACKGROUND_ACCOUNTS,
    SCENARIO_JSON,
    SEED,
    TRANSACTIONS_CSV,
    WINDOW_DAYS,
    WINDOW_END,
    WINDOW_START,
)
from ..models import Account, Dataset
from . import typologies as T
from .calibration import HI_SMALL, degree_weights, lognormal_amount
from .world import World

AGE_BANDS = ("18-25", "26-40", "41-60", "60+")


# --------------------------------------------------------------------------
# Account construction
# --------------------------------------------------------------------------


class _Identities:
    """Hands out unique phones and addresses.

    Uniqueness matters: rule G2 fires on a *shared* phone or address, so an
    accidental Faker collision between two background accounts would be
    indistinguishable from a real mule farm and would put a false positive on
    the demo graph.
    """

    def __init__(self, fake: Faker) -> None:
        self.fake = fake
        self._phones: set[str] = set()
        self._addresses: set[str] = set()

    def phone(self) -> str:
        while True:
            value = self.fake.numerify("+91-9#########")
            if value not in self._phones:
                self._phones.add(value)
                return value

    def address(self) -> str:
        while True:
            value = self.fake.address().replace("\n", ", ")
            if value not in self._addresses:
                self._addresses.add(value)
                return value

    def claim(self, phone: str, address: str) -> None:
        self._phones.add(phone)
        self._addresses.add(address)


def _make_account(
    world: World,
    ids: _Identities,
    fake: Faker,
    rng: random.Random,
    account_id: str,
    *,
    age_band: str | None = None,
    role: str = "background",
    known_suspicious: bool = False,
    dormant: bool | None = None,
) -> Account:
    open_date = (WINDOW_START - dt.timedelta(days=rng.randint(90, 2_400))).date()
    account = Account(
        account_id=account_id,
        name=fake.name(),
        open_date=open_date,
        dormancy_flag=rng.random() < 0.07 if dormant is None else dormant,
        age_band=age_band or rng.choices(AGE_BANDS, weights=(0.22, 0.34, 0.28, 0.16))[0],
        phone=ids.phone(),
        address=ids.address(),
        kyc_date=open_date + dt.timedelta(days=rng.randint(0, 45)),
        known_suspicious=known_suspicious,
        role=role,
    )
    return world.add_account(account)


def _build_accounts(world: World, ids: _Identities, fake: Faker, rng: random.Random) -> None:
    """Create every account, named roles first so their ids stay stable."""
    # -- scenario 1: the loud ring ----------------------------------------
    _make_account(world, ids, fake, rng, T.VICTIM, age_band="60+", role="victim", dormant=False)
    for mule in T.MULES:
        _make_account(world, ids, fake, rng, mule, age_band="18-25", role="mule", dormant=False)
    for ring in T.RING:
        _make_account(world, ids, fake, rng, ring, age_band="18-25", role="ring", dormant=False)
    for sender in T.FUNNEL_SENDERS:
        _make_account(world, ids, fake, rng, sender, role="funnel-sender", dormant=False)
    for payee in T.VICTIM_PAYEES:
        _make_account(world, ids, fake, rng, payee, role="payee", dormant=False)
    _make_account(world, ids, fake, rng, T.BRIDGE, role="bridge", dormant=False)
    for exit_account in T.EXITS:
        _make_account(world, ids, fake, rng, exit_account, role="ring-exit", dormant=False)
    _make_account(
        world, ids, fake, rng, T.WATCHLIST, role="watchlist", known_suspicious=True, dormant=False
    )

    # -- scenario 2: account takeover -------------------------------------
    _make_account(world, ids, fake, rng, T.ATO_VICTIM, age_band="41-60", role="ato", dormant=False)
    _make_account(world, ids, fake, rng, T.ATO_DESTINATION, role="ato-destination", dormant=False)

    # -- act 3: the stealth ring. 26-40 so S3 cannot apply, each with its own
    #    phone and address so G2 cannot. ----------------------------------
    for stealth in T.STEALTH:
        _make_account(
            world, ids, fake, rng, stealth, age_band="26-40", role="stealth", dormant=False
        )
    for feeder in T.STEALTH_FEEDERS:
        _make_account(world, ids, fake, rng, feeder, role="stealth-feeder", dormant=False)

    # -- background ------------------------------------------------------
    for index in range(1, N_BACKGROUND_ACCOUNTS + 1):
        _make_account(world, ids, fake, rng, f"ACC-G{index:04d}", role="background")


# --------------------------------------------------------------------------
# Background traffic
# --------------------------------------------------------------------------

#: Accounts kept out of random background traffic.
#:
#: The watchlist and bridge accounts are excluded so G1's two-hop neighbourhood
#: stays exactly {bridge, ring hub} -- one stray random edge into the watchlist
#: would spray +15 across unrelated accounts. The stealth ring and its feeders
#: are excluded so no accidental path can form between them and the watchlist,
#: which would trip G1 and destroy the "no rule fires" claim that Act 3 rests on.
def _excluded_from_background() -> frozenset[str]:
    return frozenset(
        (T.WATCHLIST, T.BRIDGE)
        + T.STEALTH
        + T.STEALTH_FEEDERS
    )


def _random_timestamp(rng: random.Random) -> dt.datetime:
    day = rng.randrange(WINDOW_DAYS)
    hour = rng.choices(range(24), weights=HI_SMALL.hour_weights)[0]
    return WINDOW_START + dt.timedelta(
        days=day, hours=hour, minutes=rng.randrange(60), seconds=rng.randrange(60)
    )


def _plant_background_traffic(world: World, rng: random.Random) -> None:
    """Ordinary retail traffic, shaped to the HI-Small calibration.

    Deliberately *irregular*: amounts are lognormal, forwarding delays are
    uniform over days, and counterparties are re-used across the window. That
    irregularity is what the stealth ring's metronomic behaviour stands out
    against -- if the background were as tidy as the ring, the Isolation Forest
    would have nothing to separate.
    """
    excluded = _excluded_from_background()
    pool = sorted(
        a.account_id
        for a in world.accounts
        if a.account_id not in excluded and a.role in {"background", "payee", "funnel-sender"}
    )
    degrees, weights = degree_weights()

    for account_id in pool:
        degree = rng.choices(degrees, weights=weights)[0]
        candidates = [c for c in pool if c != account_id]
        counterparties = rng.sample(candidates, k=min(degree, len(candidates)))
        for counterparty in counterparties:
            for _ in range(rng.randint(1, 4)):
                # Direction varies so in-degree and out-degree decorrelate,
                # which keeps the fan-in/fan-out symmetry feature meaningful.
                if rng.random() < 0.5:
                    src, dst = account_id, counterparty
                else:
                    src, dst = counterparty, account_id
                world.add_txn(
                    src,
                    dst,
                    lognormal_amount(rng),
                    _random_timestamp(rng),
                    rng.choices(
                        list(HI_SMALL.channel_weights),
                        weights=list(HI_SMALL.channel_weights.values()),
                    )[0],
                )


def _plant_background_sessions(world: World, rng: random.Random) -> None:
    """One stable device per background account.

    No shared fingerprints (G2) and no failed-login runs or password resets
    (A1/A2) in the background: the only accounts carrying those signals are the
    ones the scenarios plant them on, so every A-rule and G2 hit in the demo is
    traceable to a scenario rather than to noise.
    """
    excluded = _excluded_from_background() | {T.ATO_VICTIM} | set(T.MULES)
    for account in sorted(world.accounts, key=lambda a: a.account_id):
        if account.account_id in excluded:
            continue
        fingerprint = f"DFP-BG-{account.account_id[-4:]}"
        ip = f"10.{rng.randrange(256)}.{rng.randrange(256)}.{rng.randrange(1, 255)}"
        for _ in range(rng.randint(4, 9)):
            world.add_session(account.account_id, fingerprint, ip, _random_timestamp(rng))


def _plant_background_beneficiaries(world: World, rng: random.Random) -> None:
    """Payees registered long before the window, so S1/S3 see no new payee."""
    excluded = _excluded_from_background()
    known: set[tuple[str, str]] = {(b.account, b.payee) for b in world.beneficiaries}
    for txn in world.transactions:
        if txn.from_account in excluded or txn.tag:
            continue
        pair = (txn.from_account, txn.to_account)
        if pair in known:
            continue
        known.add(pair)
        world.add_beneficiary(
            txn.from_account,
            txn.to_account,
            WINDOW_START - dt.timedelta(days=rng.randint(30, 900)),
        )


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def build_world() -> tuple[Dataset, list[T.PlantedStructure]]:
    """Construct the whole world in memory. Pure and deterministic."""
    rng = random.Random(SEED)
    fake = Faker("en_IN")
    Faker.seed(SEED)

    world = World(rng)
    ids = _Identities(fake)

    _build_accounts(world, ids, fake, rng)
    _plant_background_traffic(world, rng)
    _plant_background_sessions(world, rng)

    structures = [
        T.plant_loud_ring(world),
        T.plant_ato_pair(world),
        T.plant_stealth_ring(world),
    ]

    _plant_background_beneficiaries(world, rng)

    # Sort everything into a canonical order. Ties broken by id so the output
    # never depends on insertion order.
    world.accounts.sort(key=lambda a: a.account_id)
    world.transactions.sort(key=lambda t: (t.timestamp, t.txn_id))
    world.device_sessions.sort(key=lambda s: (s.timestamp, s.session_id))
    world.beneficiaries.sort(key=lambda b: (b.added_timestamp, b.account, b.payee))

    dataset = Dataset(
        accounts=world.accounts,
        transactions=world.transactions,
        device_sessions=world.device_sessions,
        beneficiaries=world.beneficiaries,
    )
    return dataset, structures


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def _write_csv(path, rows, fieldnames) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_dataset(dataset: Dataset, structures: list[T.PlantedStructure]) -> None:
    _write_csv(
        ACCOUNTS_CSV,
        ({**asdict(a), "open_date": a.open_date.isoformat(), "kyc_date": a.kyc_date.isoformat()} for a in dataset.accounts),
        ["account_id", "name", "open_date", "dormancy_flag", "age_band", "phone", "address", "kyc_date", "known_suspicious", "role"],
    )
    _write_csv(
        TRANSACTIONS_CSV,
        ({**asdict(t), "timestamp": t.timestamp.isoformat()} for t in dataset.transactions),
        ["txn_id", "from_account", "to_account", "amount", "timestamp", "channel", "tag"],
    )
    _write_csv(
        DEVICE_SESSIONS_CSV,
        ({**asdict(s), "timestamp": s.timestamp.isoformat()} for s in dataset.device_sessions),
        ["session_id", "account", "device_fingerprint", "ip", "login_result", "timestamp", "password_reset_flag"],
    )
    _write_csv(
        BENEFICIARIES_CSV,
        ({**asdict(b), "added_timestamp": b.added_timestamp.isoformat()} for b in dataset.beneficiaries),
        ["account", "payee", "added_timestamp"],
    )

    manifest = {
        "seed": SEED,
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "counts": {
            "accounts": len(dataset.accounts),
            "transactions": len(dataset.transactions),
            "device_sessions": len(dataset.device_sessions),
            "beneficiaries": len(dataset.beneficiaries),
        },
        "calibration_reference": (
            "IBM Transactions for Anti Money Laundering (AML), HI-Small variant; "
            "Altman et al., NeurIPS 2023 Datasets and Benchmarks"
        ),
        "structures": [
            {
                "key": s.key,
                "label": s.label,
                "primary_account": s.primary_account,
                "account_ids": list(s.account_ids),
                "expected_rules": list(s.expected_rules),
                "narrative": s.narrative,
            }
            for s in structures
        ],
        "stealth_evasions": [
            {"rule": rule, "margin": margin} for rule, margin in T.STEALTH_EVASIONS
        ],
    }
    SCENARIO_JSON.parent.mkdir(parents=True, exist_ok=True)
    SCENARIO_JSON.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    dataset, structures = build_world()
    write_dataset(dataset, structures)
    print(
        f"accounts={len(dataset.accounts)} "
        f"transactions={len(dataset.transactions)} "
        f"sessions={len(dataset.device_sessions)} "
        f"beneficiaries={len(dataset.beneficiaries)}"
    )


if __name__ == "__main__":
    main()
