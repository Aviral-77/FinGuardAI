"""The three structures planted into the generated world.

Design discipline
-----------------
The generator plants **behaviour**, never verdicts. Nothing here writes a score,
a rule id or a label that the engine later reads back. Each structure is shaped
so that the independently-written rules in ``app.engine.rules`` will or will not
fire on it, and ``tests/test_scenario.py`` pins the resulting scores. If a score
comes out wrong, the fix belongs in this file -- never in a rule.

The three structures
--------------------
1. ``plant_loud_ring``   -- the scripted demo. Fires S3, S1, M1, M2, G2, G3 in
   that order, exactly as CLAUDE.md section 6 specifies.
2. ``plant_ato_pair``    -- the 30-second account-takeover scenario: A2, A1, S2.
3. ``plant_stealth_ring`` -- eight accounts engineered to slip under *every*
   rule threshold. No rule fires. Only the anomaly model sees it. This is the
   Act 3 headline, and the margins by which it evades each rule are documented
   inline so the evasion is auditable rather than accidental.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..config import WINDOW_END, WINDOW_START

if TYPE_CHECKING:  # pragma: no cover
    from .world import World


def at(day: float, hour: int = 0, minute: int = 0) -> dt.datetime:
    """A timestamp expressed as an offset from the dataset window start."""
    return WINDOW_START + dt.timedelta(days=day, hours=hour, minutes=minute)


@dataclass(frozen=True)
class PlantedStructure:
    """What was planted, for the scenario manifest and the demo UI."""

    key: str
    label: str
    account_ids: tuple[str, ...]
    primary_account: str
    expected_rules: tuple[str, ...]
    narrative: str


# ==========================================================================
# 1. The loud ring -- the scripted demo (CLAUDE.md section 6)
# ==========================================================================

VICTIM = "ACC-V001"
MULES = ("ACC-M001", "ACC-M002", "ACC-M003")
PRIMARY_MULE = MULES[0]
RING = tuple(f"ACC-R{i:03d}" for i in range(1, 12))  # 11 accounts -> G3 needs >10
RING_HUB = RING[0]
FUNNEL_SENDERS = tuple(f"ACC-F{i:03d}" for i in range(1, 7))  # 6 unrelated senders
VICTIM_PAYEES = ("ACC-P001", "ACC-P002")
BRIDGE = "ACC-B001"
WATCHLIST = "ACC-W001"
#: Where the ring cashes out to -- outside the ring, so no short cycle forms.
EXITS = ("ACC-E001", "ACC-E002")

#: Device fingerprint shared by three mule accounts -> G2.
SHARED_MULE_DEVICE = "DFP-7A31-MULE-SHARED"


def plant_loud_ring(world: World) -> PlantedStructure:
    """Plant the scripted scenario.

    Firing order, by timestamp, matching CLAUDE.md section 6:

    ===== ========================= ====== ==================================
    When  Rule                      Points Account
    ===== ========================= ====== ==================================
    d22   S3 elderly / vulnerable      +15 victim
    d23   S1 new beneficiary, high     +20 victim      -> 35, Enhanced monitoring
    d23   M1 rapid fund movement       +25 primary mule
    d24   M2 multiple source accts     +20 primary mule
    d24   G2 shared identifiers        +20 primary mule -> 65, Step-up auth
    d25   G3 emerging ring             +35 ring hub     -> 95, FREEZE (climax)
    ===== ========================= ====== ==================================

    The hub also picks up M1 + M2 (it is itself a collector) and G1 (two hops
    from the watchlist account), which is what puts it at 60 before G3 lands and
    makes G3 the rule that carries it across 86.
    """
    # -- victim's ordinary history: a low average transfer value, so that the
    #    later transfer reads as >5x average to S1 --------------------------
    victim_history_amounts = [4_200, 3_850, 5_100, 4_450, 3_990, 5_400, 4_100, 4_910]
    for index, amount in enumerate(victim_history_amounts):
        world.add_txn(
            VICTIM,
            VICTIM_PAYEES[index % len(VICTIM_PAYEES)],
            amount,
            at(2 + index * 2.3, 10, 15 * index % 60),
            "ACH",
            tag="victim-history",
        )
    # Long-standing payees, added well before the window's action.
    for payee in VICTIM_PAYEES:
        world.add_beneficiary(VICTIM, payee, at(0, 9))

    # -- the mule receives from six unrelated senders over the prior week.
    #    Amounts sit inside a +/-20% band around ~162k, which is what M2 keys
    #    on; the sixth lands on d24 so M2 fires *after* M1. -----------------
    funnel = [
        (FUNNEL_SENDERS[0], 162_000, at(17, 11, 20)),
        (FUNNEL_SENDERS[1], 158_500, at(18, 14, 5)),
        (FUNNEL_SENDERS[2], 171_000, at(19, 9, 40)),
        (FUNNEL_SENDERS[3], 155_200, at(20, 16, 15)),
        (FUNNEL_SENDERS[4], 166_400, at(21, 12, 50)),
    ]
    for sender, amount, when in funnel:
        world.add_txn(sender, PRIMARY_MULE, amount, when, "Wire", tag="funnel-in")

    # -- S3: new payee added, then multiple high-value transfers within 48h --
    world.add_beneficiary(VICTIM, PRIMARY_MULE, at(22, 10))
    world.add_txn(VICTIM, VICTIM_PAYEES[0], 95_000, at(22, 15), "Wire", tag="scam-s3")
    world.add_txn(VICTIM, VICTIM_PAYEES[1], 110_000, at(22, 19, 30), "Wire", tag="scam-s3")

    # -- S1: first transfer to the newly added payee, >5x the victim's average
    world.add_txn(VICTIM, PRIMARY_MULE, 275_000, at(23, 6), "Wire", tag="scam-s1")

    # -- M1: 87% of the accumulated balance leaves within 24h ---------------
    #    Credits to this point: 813,100 (funnel) + 275,000 (victim) = 1,088,100.
    #    Debits below total 946,650 = 87.0%, crossing the 80% line on the
    #    18:00 transfer -- which is the moment M1 fires.
    outflow = [
        (MULES[1], 210_000, at(23, 7, 30)),
        (MULES[2], 195_000, at(23, 9, 45)),
        (RING_HUB, 235_000, at(23, 12, 10)),
        (RING[1], 165_000, at(23, 15, 20)),
        (RING[2], 141_650, at(23, 18, 0)),
    ]
    for target, amount, when in outflow:
        world.add_txn(PRIMARY_MULE, target, amount, when, "Wire", tag="mule-out")

    # -- M2: the sixth clustered sender arrives, taking unique senders past 5
    world.add_txn(FUNNEL_SENDERS[5], PRIMARY_MULE, 159_800, at(24, 9), "Wire", tag="funnel-in")

    # -- secondary mules also pass funds through quickly (they earn M1 too) --
    world.add_txn(MULES[1], RING[3], 178_000, at(23, 13, 40), "Wire", tag="mule-out")
    world.add_txn(MULES[2], RING[4], 166_000, at(23, 16, 25), "Wire", tag="mule-out")

    # -- G2: three mule accounts seen on one device fingerprint. The third
    #    sighting on d24 12:00 is what makes the rule fire. -----------------
    world.add_session(MULES[0], SHARED_MULE_DEVICE, "203.0.113.44", at(20, 8))
    world.add_session(MULES[1], SHARED_MULE_DEVICE, "203.0.113.44", at(22, 13))
    world.add_session(MULES[2], SHARED_MULE_DEVICE, "203.0.113.44", at(24, 12))

    # -- G1: the hub sits two hops from a previously-reported account, via a
    #    bridge. The bridge->watchlist edge is old; the hub->bridge edge on
    #    d24 15:00 is what closes the path, before G3 fires. ---------------
    world.add_txn(BRIDGE, WATCHLIST, 47_000, at(11, 10), "Wire", tag="watchlist-link")
    world.add_txn(RING_HUB, BRIDGE, 92_000, at(24, 15), "Wire", tag="proximity-link")

    # -- M2 for the hub: six ring members feed it in a tight amount band ----
    hub_feed = [102_000, 98_500, 105_400, 96_800, 101_300, 99_700]
    for index, amount in enumerate(hub_feed):
        world.add_txn(
            RING[5 + index],
            RING_HUB,
            amount,
            at(24, 10, 12 * index),
            "ACH",
            tag="ring-collect",
        )

    # -- M1 for the hub: 85% of its balance cashes out of the ring ---------
    #    The exits deliberately leave the ring rather than looping back to
    #    R002-R005. A hub that pays its own members back creates short cycles,
    #    which would hand the hub M3 (+30) before the ring is even detected --
    #    and the hub would then already be past 86 when G3 lands, costing the
    #    demo its climax. Rings cash out; that is also what really happens.
    hub_out = [
        (EXITS[0], 214_000, at(24, 18, 10)),
        (EXITS[1], 198_000, at(24, 20, 35)),
        (EXITS[0], 187_000, at(24, 22, 15)),
        (EXITS[1], 112_000, at(25, 3, 40)),
    ]
    for target, amount, when in hub_out:
        world.add_txn(RING_HUB, target, amount, when, "Wire", tag="ring-out")

    # -- G3: eleven accounts moving on near-identical timing and routing.
    #    Whole-day steps keep every pass at 14:00 -- the shared hour *is* the
    #    signal G3 keys on, and a half-day step would scatter the passes across
    #    the clock and make the ring look no more coordinated than background
    #    traffic. The third pass on d26 is the last rule to fire.
    #    The hub has no *outgoing* edge into the ring: layers feed forward into
    #    it and it cashes out. Give the hub an outgoing ring edge and short
    #    cycles form back through it, which hands it M3 (+30) early and puts it
    #    past 86 before G3 ever runs -- so the chain deliberately starts at
    #    RING[1] and terminates at the hub.
    for cycle in range(3):
        for index in range(1, len(RING)):
            account = RING[index]
            target = RING[(index + 1) % len(RING)]
            world.add_txn(
                account,
                target,
                88_000 + index * 1_100 + cycle * 2_400,
                at(24 + cycle, 14, (index * 4) % 60),
                "ACH",
                tag="ring-cycle",
            )

    # -- M3: a tight round-trip between three ring members, closing well
    #    inside 72h. The 11-account ring cycle itself is too long to register
    #    as circular; this is the short loop that does. -------------------
    round_trip = (
        (RING[6], RING[7], 96_000, at(25, 9, 20)),
        (RING[7], RING[8], 93_500, at(25, 20, 5)),
        (RING[8], RING[6], 91_200, at(26, 11, 45)),
    )
    for source, target, amount, when in round_trip:
        world.add_txn(source, target, amount, when, "ACH", tag="ring-roundtrip")

    accounts = (
        (VICTIM,)
        + MULES
        + RING
        + FUNNEL_SENDERS
        + VICTIM_PAYEES
        + EXITS
        + (BRIDGE, WATCHLIST)
    )
    return PlantedStructure(
        key="loud_ring",
        label="Scam-to-mule ring",
        account_ids=accounts,
        primary_account=RING_HUB,
        expected_rules=("S3", "S1", "M1", "M2", "G2", "G1", "G3"),
        narrative=(
            "An elderly customer is talked into transferring funds to a newly "
            "added payee. The receiving account pushes 87% of its balance out "
            "within a day, having collected from six unrelated senders that "
            "week, and shares a device fingerprint with two more mules. The "
            "funds land in an eleven-account cluster moving on identical "
            "timing -- the ring."
        ),
    )


# ==========================================================================
# 2. Account takeover -- the 30-second second scenario
# ==========================================================================

ATO_VICTIM = "ACC-T001"
ATO_DESTINATION = "ACC-T002"
ATO_HOME_DEVICE = "DFP-C4E9-HOME"
ATO_ATTACKER_DEVICE = "DFP-F002-UNKNOWN"


def plant_ato_pair(world: World) -> PlantedStructure:
    """New device login -> password reset -> immediate transfer.

    Fires A2 (+20), then A1 (+30), then S2 (+25) = 75 -> Manual fraud review.

    Note on the brief: CLAUDE.md section 6 describes this scenario as
    "A1 (+30) -> Temporary Transaction Hold", but its own score table in
    section 4 puts 30 points in the 0-30 "Allow transaction" band. A1 alone
    cannot produce a hold. The takeover here therefore plays out as it
    realistically would -- credential stuffing (A2), then the reset and
    transfer (A1), then a transfer that is off-pattern in both device and
    value (S2) -- which reaches 75 and a review posture.
    """
    # -- a settled history: same device, same IP range, modest transfers ----
    for index in range(10):
        world.add_txn(
            ATO_VICTIM,
            ATO_DESTINATION if index % 3 == 0 else "ACC-P001",
            5_400 + index * 190,
            at(2 + index * 2.1, 12, (index * 7) % 60),
            "ACH",
            tag="ato-history",
        )
        world.add_session(
            ATO_VICTIM, ATO_HOME_DEVICE, "198.51.100.17", at(2 + index * 2.1, 11, 40)
        )
    world.add_beneficiary(ATO_VICTIM, ATO_DESTINATION, at(1, 8))

    # -- A2: five failed logins, then a success from a different IP/device --
    for index in range(5):
        world.add_session(
            ATO_VICTIM,
            ATO_ATTACKER_DEVICE,
            "185.220.101.9",
            at(26, 20, 10 + index * 5),
            login_result="failure",
        )
    world.add_session(ATO_VICTIM, ATO_ATTACKER_DEVICE, "185.220.101.9", at(26, 20, 41))

    # -- A1: password reset on the new device, then an outbound transfer ----
    world.add_session(
        ATO_VICTIM,
        ATO_ATTACKER_DEVICE,
        "185.220.101.9",
        at(26, 20, 55),
        password_reset_flag=True,
    )
    # -- S2 rides the same transfer: unfamiliar device, ~24x the usual value.
    world.add_txn(ATO_VICTIM, ATO_DESTINATION, 148_000, at(26, 21, 10), "Wire", tag="ato-drain")

    return PlantedStructure(
        key="ato",
        label="Account takeover",
        account_ids=(ATO_VICTIM, ATO_DESTINATION),
        primary_account=ATO_VICTIM,
        expected_rules=("A2", "A1", "S2"),
        narrative=(
            "Five failed logins, then a success from an unfamiliar device and "
            "IP, a password reset fifteen minutes later, and a transfer worth "
            "24x this customer's usual within the hour."
        ),
    )


# ==========================================================================
# 3. The stealth ring -- what the rules cannot see
# ==========================================================================

STEALTH = tuple(f"ACC-X{i:03d}" for i in range(1, 9))  # 8 accounts: G3 needs >10
STEALTH_FEEDERS = tuple(f"ACC-XF{i:03d}" for i in range(1, 9))

#: Every evasion margin, stated once so the design is auditable.
STEALTH_EVASIONS: tuple[tuple[str, str], ...] = (
    ("M1", "forwards 68-74% of each credit, and only after 26-33h (needs >80% of balance within 24h)"),
    ("M2", "two unique external senders per account, amounts spread far wider than +/-20% (needs >5, clustered)"),
    ("M3", "an 8-account loop, longer than the 6-hop cycle search, so no circuit closes (needs a return within 72h)"),
    ("S1", "no transfer exceeds 2.6x the account's own average (needs >5x)"),
    ("S2", "one consistent device and IP per account throughout (needs a device/location change)"),
    ("S3", "all members are in the 26-40 age band (needs an elderly/vulnerable profile)"),
    ("A1", "no password resets, no new-device logins (needs both plus a transfer)"),
    ("A2", "no failed logins at all (needs 5 then a success elsewhere)"),
    ("G1", "at least 4 hops from the watchlist account (needs within 2)"),
    ("G2", "unique device fingerprint, phone and address per account (needs a shared identifier)"),
    ("G3", "8 accounts (needs a cluster of >10)"),
)


def plant_stealth_ring(world: World) -> PlantedStructure:
    """Eight accounts that no rule fires on, and the anomaly model still finds.

    Every threshold above is missed deliberately and by a visible margin -- see
    ``STEALTH_EVASIONS``. What the ring cannot disguise is its *shape*: a
    near-constant pass-through ratio, a forwarding latency clustered inside a
    few hours, counterparties that are all new inside the window, and fan-in
    almost exactly matching fan-out. No single one of those is suspicious.
    Together they put these eight accounts in the tail of the Isolation Forest,
    and because they are also connected to each other, they surface as a
    *network* rather than eight unrelated oddities.

    Kept structurally isolated: members transact only with each other and with
    dedicated feeders, so no accidental path to the watchlist account can form
    and trip G1.
    """
    # Deterministic per-account parameters -- written out rather than sampled,
    # so the ring is identical on every run without depending on RNG ordering.
    #
    # Each member runs to its own script: forward a fixed fraction of whatever
    # arrives, at its own fixed hour of the day, at least ``min_hold`` hours
    # later. Every parameter here is chosen to sit under a rule threshold, and
    # what is left over is the thing no rule measures -- consistency.
    pass_through = (0.71, 0.69, 0.73, 0.70, 0.72, 0.68, 0.74, 0.70)
    operating_hour = (9, 11, 14, 16, 10, 15, 12, 17)
    min_hold_hours = (26, 30, 27, 33, 28, 31, 26, 29)
    seed_amounts = (186_400, 174_900, 218_300, 165_200, 197_100, 208_600, 171_500, 192_800)
    #: Stop cascading once a hop falls below this -- it would be lost in noise.
    floor = 6_000.0

    def next_operating_slot(after: dt.datetime, hour: int, min_hold: int) -> dt.datetime:
        """The account's next working slot at least ``min_hold`` hours out."""
        earliest = after + dt.timedelta(hours=min_hold)
        slot = earliest.replace(hour=hour, minute=0, second=0, microsecond=0)
        if slot < earliest:
            slot += dt.timedelta(days=1)
        return slot

    # -- seed credits: two unique feeders per account. Two is far short of M2's
    #    ">5 unique senders", and the amounts are dispersed so the clustering
    #    half of the rule is missed as well -- the ring evades both halves,
    #    not just the easier one. -----------------------------------------
    pending: list[tuple[dt.datetime, int, float]] = []
    for index, account in enumerate(STEALTH):
        for slot in range(2):
            feeder = STEALTH_FEEDERS[(index * 2 + slot) % len(STEALTH_FEEDERS)]
            amount = round(seed_amounts[index] * (0.62 if slot else 1.0), 2)
            when = at(3 + index * 0.4 + slot * 8.0, 10 + slot * 3, (index * 13 + slot * 19) % 60)
            world.add_txn(feeder, account, amount, when, "ACH", tag="stealth-in")
            pending.append((when, index, amount))

    # -- the cascade. Every credit is forwarded individually, so the holding
    #    period and the forwarded fraction are the *same every time*.
    #
    #    That is what makes the ring findable without being ruleable. M1 cannot
    #    fire: each hop moves 68-74% of the credit that funded it, so the share
    #    of the balance leaving never approaches 80% however the amounts fall,
    #    and the 26-33h delay clears the 24h window independently -- two
    #    margins, not one. M3 cannot fire either: eight members means the loop
    #    is longer than the 6-account cycle search, so money never completes a
    #    circuit inside 72h. Every edge of the cycle still exists, which is why
    #    the *graph* shows a ring even though no rule does.
    #    The chain is cut off after a few hops so these accounts do not end up
    #    transacting far more than anyone else. A ring that stood out on sheer
    #    volume would be separable for a trivial reason, and the claim being
    #    made here is that it is separable on *shape*.
    max_hops = 3
    queue: list[tuple[dt.datetime, int, float, int]] = [
        (when, index, amount, 0) for when, index, amount in pending
    ]
    queue.sort(key=lambda item: (item[0], item[1]))
    while queue:
        when, index, amount, hop = queue.pop(0)
        if hop >= max_hops:
            continue
        forwarded = round(amount * pass_through[index], 2)
        if forwarded < floor:
            continue
        depart = next_operating_slot(when, operating_hour[index], min_hold_hours[index])
        if depart >= WINDOW_END:
            continue
        target_index = (index + 1) % len(STEALTH)
        world.add_txn(
            STEALTH[index],
            STEALTH[target_index],
            forwarded,
            depart,
            "ACH",
            tag="stealth-hop",
        )
        queue.append((depart, target_index, forwarded, hop + 1))
        queue.sort(key=lambda item: (item[0], item[1]))

    # -- a few chords across the loop. Without them the ring is a bare cycle,
    #    which has no triangles at all, and the graph layer would see less
    #    cohesion here than in ordinary traffic. Real mule rings are not neat
    #    circles. Each chord skips one member, so the shortest circuit is still
    #    four hops of 26h+ -- comfortably outside M3's 72h return window.
    for source_index, target_index, amount, day in (
        (0, 2, 41_500.0, 12.0),
        (2, 4, 38_900.0, 15.0),
        (4, 6, 36_200.0, 18.0),
        (6, 0, 34_800.0, 21.0),
    ):
        world.add_txn(
            STEALTH[source_index],
            STEALTH[target_index],
            amount,
            at(day, operating_hour[source_index], 20),
            "ACH",
            tag="stealth-chord",
        )

    # -- one consistent device and IP per member: S2 and G2 both need change
    #    or sharing, and there is neither. ---------------------------------
    for index, account in enumerate(STEALTH):
        for visit in range(6):
            world.add_session(
                account,
                f"DFP-STEALTH-{index:02d}",
                f"192.0.2.{40 + index}",
                at(4 + visit * 3.4 + index * 0.2, 8, (index * 13) % 60),
            )

    return PlantedStructure(
        key="stealth_ring",
        label="Stealth mule network",
        account_ids=STEALTH,
        primary_account=STEALTH[0],
        expected_rules=(),  # by construction: none
        narrative=(
            "Eight accounts moving money in a closed loop, every parameter "
            "tuned to sit just under a reporting threshold. No rule fires. "
            "The anomaly model flags all eight on the shape of their behaviour "
            "-- a pass-through ratio that never varies, a forwarding delay "
            "clustered inside six hours, and counterparties that are all new "
            "-- and the graph layer shows they are connected."
        ),
    )
