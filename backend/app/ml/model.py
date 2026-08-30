"""The anomaly model -- the "CATCH" stage.

An Isolation Forest over the behavioural features in :mod:`app.ml.features`.
Unsupervised on purpose: there are no labels in production, and a supervised
model could only learn the patterns someone already wrote a rule for.

Where this sits relative to the rule engine
-------------------------------------------
Beside it, never inside it. The anomaly score is its own column and never adds
points to a rule score. CLAUDE.md's non-negotiable is that every point traces
to a named rule; folding a model output into the score would make the total
unauditable, and "the model thought so" is not something an analyst can put in
a case file. What the model produces instead is a separate finding with its own
action lane (``ML_REVIEW``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest

from ..config import (
    IFOREST_CONTAMINATION,
    IFOREST_MAX_SAMPLES,
    IFOREST_N_ESTIMATORS,
    IFOREST_RANDOM_STATE,
    ML_ELEVATED_QUANTILE,
)
from ..models import MLFinding
from .explain import explain_account
from .features import FeatureTable


@dataclass
class AnomalyResult:
    findings: dict[str, MLFinding]
    table: FeatureTable
    #: Population mean and standard deviation per feature, for explanation.
    means: list[float]
    stdevs: list[float]

    @property
    def anomalous_accounts(self) -> list[str]:
        return sorted(a for a, f in self.findings.items() if f.is_anomalous)


def run_anomaly_model(table: FeatureTable) -> AnomalyResult:
    """Fit and score in one pass.

    There is no train/serve split: the model is fitted on the same population it
    scores, which is what an unsupervised outlier detector is for -- "unusual
    compared to this bank's own customers this month".

    Fully deterministic. ``random_state`` and ``max_samples`` are pinned, the
    feature column order is fixed, and accounts are scored in sorted order, so
    the ranking is identical on every run.
    """
    matrix = np.asarray(table.rows, dtype=np.float64)
    if matrix.size == 0:
        return AnomalyResult({}, table, [], [])

    forest = IsolationForest(
        n_estimators=IFOREST_N_ESTIMATORS,
        contamination=IFOREST_CONTAMINATION,
        max_samples=min(IFOREST_MAX_SAMPLES, matrix.shape[0]),
        random_state=IFOREST_RANDOM_STATE,
        bootstrap=False,
        n_jobs=1,
    )
    forest.fit(matrix)

    # decision_function: negative = outlier. Flip and min-max to [0, 1] so the
    # UI can render it as "how anomalous", higher being worse.
    raw = forest.decision_function(matrix)
    flagged = forest.predict(matrix) == -1
    lo, hi = float(raw.min()), float(raw.max())
    span = (hi - lo) or 1.0
    normalised = [(hi - float(value)) / span for value in raw]

    means = [float(v) for v in matrix.mean(axis=0)]
    stdevs = [float(v) for v in matrix.std(axis=0)]

    order = sorted(
        range(len(table.account_ids)),
        key=lambda i: (-normalised[i], table.account_ids[i]),
    )
    rank_of = {index: position + 1 for position, index in enumerate(order)}

    elevated_cutoff = max(1, round(ML_ELEVATED_QUANTILE * len(table.account_ids)))

    findings: dict[str, MLFinding] = {}
    for index, account_id in enumerate(table.account_ids):
        findings[account_id] = MLFinding(
            account_id=account_id,
            anomaly_score=round(normalised[index], 6),
            is_anomalous=bool(flagged[index]),
            is_elevated=rank_of[index] <= elevated_cutoff,
            rank=rank_of[index],
            top_features=explain_account(table.rows[index], means, stdevs),
        )
    return AnomalyResult(findings=findings, table=table, means=means, stdevs=stdevs)
