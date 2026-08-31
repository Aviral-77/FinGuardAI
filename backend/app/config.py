"""Central configuration for FinGuard AI.

Everything that makes a run reproducible lives here. The brief's working
principle is "determinism over realism": the ring must form identically on
every run, so there is exactly one seed and one clock origin for the whole
system.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

ACCOUNTS_CSV = DATA_DIR / "accounts.csv"
TRANSACTIONS_CSV = DATA_DIR / "transactions.csv"
DEVICE_SESSIONS_CSV = DATA_DIR / "device_sessions.csv"
BENEFICIARIES_CSV = DATA_DIR / "beneficiaries.csv"
SCENARIO_JSON = DATA_DIR / "scenario.json"

# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

#: Single seed for Faker and random. Changing this regenerates the entire world.
SEED = 42

#: The dataset's window. All timestamps are generated inside it, and the rule
#: engine's notion of "now" is the replay clock within this window -- never
#: ``datetime.now()``. This is what keeps rule evaluation reproducible.
WINDOW_START = dt.datetime(2026, 5, 1, 0, 0, 0)
WINDOW_DAYS = 30
WINDOW_END = WINDOW_START + dt.timedelta(days=WINDOW_DAYS)

#: Demo slice size. The brief caps this deliberately: a 5M-row graph is
#: unreadable and the ring disappears into noise.
N_BACKGROUND_ACCOUNTS = 210

# --------------------------------------------------------------------------
# Score -> action mapping (CLAUDE.md section 4)
# --------------------------------------------------------------------------

#: (inclusive_lower, inclusive_upper, action_code, human label)
SCORE_BANDS: tuple[tuple[int, int, str, str], ...] = (
    (0, 30, "ALLOW", "Allow transaction"),
    (31, 50, "ENHANCED_MONITORING", "Enhanced monitoring"),
    (51, 70, "STEP_UP_AUTH", "Step-up authentication"),
    (71, 85, "MANUAL_REVIEW", "Manual fraud review"),
    (86, 100, "FREEZE", "Temporary block / freeze"),
)

MAX_SCORE = 100

# --------------------------------------------------------------------------
# ML layer
# --------------------------------------------------------------------------

#: Isolation Forest hyperparameters. random_state is fixed so the anomaly
#: ranking is byte-identical between runs.
IFOREST_N_ESTIMATORS = 200
IFOREST_CONTAMINATION = 0.06
IFOREST_RANDOM_STATE = SEED
IFOREST_MAX_SAMPLES = 256

#: A connected component of anomalous accounts must be at least this big before
#: we are willing to call it a network rather than a handful of odd accounts.
ML_MIN_NETWORK_SIZE = 4

#: Share of the population treated as "elevated" -- not flagged outright, but
#: anomalous enough to join a cluster that has already been seeded by flagged
#: accounts. Contamination alone decides membership of a *list*; deciding the
#: extent of a *network* deserves a second, more permissive pass, or a ring is
#: reported as two fragments whenever one member scores just under the cut.
ML_ELEVATED_QUANTILE = 0.20

#: Minimum internal edge density (edges / possible edges) for a component to
#: read as a coordinated network rather than incidental co-occurrence.
ML_MIN_DENSITY = 0.20

#: A network whose highest rule score sits below this is one the deterministic
#: engine did not escalate -- the MISSED_BY_RULES headline.
ML_MISSED_MAX_RULE_SCORE = 51

# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]
