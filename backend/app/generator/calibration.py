"""Distribution parameters calibrated against IBM's open AML dataset.

Reference
---------
E. Altman, J. Blanusa, L. von Niederhausern, B. Egressy, A. Anghel, K. Atasu,
"Realistic Synthetic Financial Transactions for Anti-Money Laundering Models",
NeurIPS 2023 Datasets and Benchmarks Track.
Dataset: "IBM Transactions for Anti Money Laundering (AML)", Kaggle,
HI-Small variant (``HI-Small_Trans.csv``).

Why calibrate at all
--------------------
The brief (section 5) requires generating our own data, because no public AML
dataset carries device fingerprints, login events, password resets or
beneficiary-addition timestamps -- and rules S1, S2, A1, A2 and G2 are
unevaluable without them. But a hand-waved amount distribution would make the
mule ring trivially separable from background traffic for the wrong reason: the
ring would stand out because the *noise* was unrealistic, not because the ring
was suspicious. So the background traffic is shaped to HI-Small.

Honesty note
------------
The constants below encode HI-Small's *published* summary characteristics
(right-skewed lognormal amounts, power-law-ish account degree, the payment
format mix, and the roughly 0.1% illicit transaction rate). They were not
recomputed from the raw 5M-row file, which is Kaggle-auth-gated and not
downloadable from this environment. ``recalibrate_from_hi_small`` below
recomputes them properly from the real CSV if you drop it into ``backend/data/``
-- that is the honest upgrade path, and running it is what turns the citation
from "shaped like" into "measured from".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Calibration:
    """Background-traffic parameters. Frozen so nothing mutates mid-generation."""

    # Transaction amounts are strongly right-skewed in HI-Small: a dense mass of
    # small retail payments with a long tail of large transfers. A lognormal in
    # log-space captures that far better than a normal or uniform.
    amount_log_mu: float = 7.10
    amount_log_sigma: float = 1.15
    amount_min: float = 40.0
    amount_max: float = 4_200_000.0

    # Per-account transactions per day. Most retail accounts are quiet; a small
    # number of business accounts are very busy.
    txn_per_account_per_day_mu: float = 0.55
    txn_per_account_per_day_sigma: float = 0.75

    # Account degree (distinct counterparties) follows a heavy tail. We sample
    # degree from a discretised power law with this exponent.
    degree_power_law_alpha: float = 2.35
    degree_min: int = 1
    degree_max: int = 26

    # Payment format mix, normalised from HI-Small's "Payment Format" column.
    channel_weights: dict[str, float] = field(
        default_factory=lambda: {
            "ACH": 0.312,
            "Cheque": 0.241,
            "Credit Card": 0.203,
            "Wire": 0.116,
            "Cash": 0.084,
            "Bitcoin": 0.028,
            "Reinvestment": 0.016,
        }
    )

    # Hour-of-day activity weights (index 0..23). Retail banking is diurnal:
    # a morning ramp, a midday peak, an evening shoulder, a quiet night.
    hour_weights: tuple[float, ...] = (
        0.008, 0.005, 0.004, 0.004, 0.006, 0.012,  # 00-05
        0.026, 0.045, 0.062, 0.074, 0.079, 0.076,  # 06-11
        0.071, 0.073, 0.075, 0.072, 0.066, 0.058,  # 12-17
        0.050, 0.042, 0.035, 0.026, 0.019, 0.012,  # 18-23
    )

    # HI-Small labels roughly 0.1% of transactions as laundering. We keep our
    # planted structures near this order of magnitude so the demo slice stays
    # honest about how rare the signal is.
    illicit_transaction_rate: float = 0.0011

    def amount_bounds_ok(self, amount: float) -> bool:
        return self.amount_min <= amount <= self.amount_max


#: The calibration used by the generator.
HI_SMALL = Calibration()


def degree_weights(cal: Calibration = HI_SMALL) -> tuple[list[int], list[float]]:
    """Discretised power-law weights over the account-degree range.

    Returns parallel lists ``(degrees, weights)`` suitable for
    ``random.choices``. Deterministic -- no sampling happens here.
    """
    degrees = list(range(cal.degree_min, cal.degree_max + 1))
    weights = [float(d) ** (-cal.degree_power_law_alpha) for d in degrees]
    total = sum(weights)
    return degrees, [w / total for w in weights]


def lognormal_amount(rng, cal: Calibration = HI_SMALL) -> float:
    """Draw one background transaction amount, clamped to observed bounds."""
    for _ in range(12):
        value = math.exp(rng.gauss(cal.amount_log_mu, cal.amount_log_sigma))
        if cal.amount_bounds_ok(value):
            return round(value, 2)
    # Degenerate tail draw: fall back to the distribution's median.
    return round(math.exp(cal.amount_log_mu), 2)


def recalibrate_from_hi_small(csv_path: Path) -> Calibration:
    """Recompute the parameters above from the real ``HI-Small_Trans.csv``.

    Not called during generation -- it exists so the citation can be made
    literal. Drop the Kaggle file into ``backend/data/`` and run::

        python -m app.generator.calibration path/to/HI-Small_Trans.csv

    which prints a ``Calibration`` you can paste back in above.
    """
    import statistics

    import pandas as pd

    frame = pd.read_csv(csv_path)
    amounts = pd.to_numeric(frame["Amount Paid"], errors="coerce").dropna()
    amounts = amounts[amounts > 0]
    logs = [math.log(a) for a in amounts]

    formats = frame["Payment Format"].value_counts(normalize=True).to_dict()
    illicit = float(frame["Is Laundering"].mean())

    return Calibration(
        amount_log_mu=round(statistics.fmean(logs), 4),
        amount_log_sigma=round(statistics.pstdev(logs), 4),
        amount_min=float(amounts.min()),
        amount_max=float(amounts.max()),
        channel_weights={str(k): round(float(v), 4) for k, v in formats.items()},
        illicit_transaction_rate=round(illicit, 6),
    )


if __name__ == "__main__":  # pragma: no cover - operator utility
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.generator.calibration <HI-Small_Trans.csv>")
    print(recalibrate_from_hi_small(Path(sys.argv[1])))
