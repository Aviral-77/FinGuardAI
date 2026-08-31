"""Why the model flagged an account.

An Isolation Forest has no feature importances, and a flag an analyst cannot
interrogate is not usable evidence -- it is the exact "produces a flag rather
than an auditable explanation" gap the brief names as a competitor weakness.

So the explanation is computed separately and deterministically: rank the
account's features by how far they sit from the population, in standard
deviations, and report the largest departures with both values attached. That
is not a reconstruction of the forest's internal splits, and it is not
presented as one -- it answers "what is unusual about this account", which is
the question the analyst actually has.
"""

from __future__ import annotations

from typing import Any

from .features import FEATURE_LABELS, FEATURE_NAMES, FEATURE_UNITS

#: How many departures to report per account.
TOP_N = 4

#: Below this many standard deviations a feature is unremarkable and is not
#: worth an analyst's attention.
MIN_Z = 1.0


def explain_account(
    row: list[float], means: list[float], stdevs: list[float]
) -> list[dict[str, Any]]:
    """The features on which this account most departs from the population."""
    scored: list[tuple[float, dict[str, Any]]] = []
    for index, name in enumerate(FEATURE_NAMES):
        stdev = stdevs[index]
        if stdev <= 1e-9:
            continue  # constant across the population: says nothing
        z = (row[index] - means[index]) / stdev
        if abs(z) < MIN_Z:
            continue
        scored.append(
            (
                abs(z),
                {
                    "feature": name,
                    "label": FEATURE_LABELS[name],
                    "unit": FEATURE_UNITS[name],
                    "value": round(row[index], 4),
                    "population_mean": round(means[index], 4),
                    "z_score": round(z, 2),
                    "direction": "above" if z > 0 else "below",
                },
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]["feature"]))
    return [payload for _, payload in scored[:TOP_N]]


def describe(features: list[dict[str, Any]]) -> str:
    """One sentence an analyst can read, built from the top departures."""
    if not features:
        return "No individual behaviour departs materially from the population."
    parts = [
        f"{f['label']} is {abs(f['z_score']):.1f} standard deviations "
        f"{f['direction']} the population ({f['value']} against {f['population_mean']})"
        for f in features[:2]
    ]
    return "Flagged because " + "; and ".join(parts) + "."
