"""Central configuration for FinGuard AI.

Everything that makes a run reproducible lives here. The brief's working
principle is "determinism over realism": the ring must form identically on
every run, so there is exactly one seed and one clock origin for the whole
system.

Deployment knobs, secrets and the AI-layer switches read from the environment
(loaded from a ``.env`` file if one is present), so nothing sensitive is
committed and the demo can be re-pointed without touching code. What stays
hard-coded here is the *audit contract* the brief calls non-negotiable: the
rule point values live with the rules, and the score-band thresholds below are
fixed. Those are the numbers a judge is invited to check; an env var that could
silently move a band would defeat the point.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from dotenv import load_dotenv

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

# Load ``backend/.env`` (then any ``.env`` up the tree) before reading vars.
# ``override=False`` so a real exported environment variable always wins over
# the file -- the file is a convenience, not an authority.
load_dotenv(BACKEND_DIR / ".env", override=False)
load_dotenv(override=False)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default

ACCOUNTS_CSV = DATA_DIR / "accounts.csv"
TRANSACTIONS_CSV = DATA_DIR / "transactions.csv"
DEVICE_SESSIONS_CSV = DATA_DIR / "device_sessions.csv"
BENEFICIARIES_CSV = DATA_DIR / "beneficiaries.csv"
SCENARIO_JSON = DATA_DIR / "scenario.json"

# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

#: Single seed for Faker and random. Changing this regenerates the entire world.
SEED = _env_int("FINGUARD_SEED", 42)

#: The dataset's window. All timestamps are generated inside it, and the rule
#: engine's notion of "now" is the replay clock within this window -- never
#: ``datetime.now()``. This is what keeps rule evaluation reproducible.
WINDOW_START = dt.datetime(2026, 5, 1, 0, 0, 0)
WINDOW_DAYS = 30
WINDOW_END = WINDOW_START + dt.timedelta(days=WINDOW_DAYS)

#: Demo slice size. The brief caps this deliberately: a 5M-row graph is
#: unreadable and the ring disappears into noise.
N_BACKGROUND_ACCOUNTS = _env_int("FINGUARD_BACKGROUND_ACCOUNTS", 210)

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

#: Master switch for the anomaly layer. The DEMO-SPEC deliberately runs the
#: stage demo with no ML -- "the rules do the detection and the score does the
#: talking". But the layer (the stealth-ring-the-rules-miss result) is kept in
#: the codebase and can be switched back on for the batch/replay analysis via
#: ``.env``. The live presenter demo forces it off regardless of this default.
ML_ENABLED = _env_bool("FINGUARD_ML_ENABLED", True)

#: Isolation Forest hyperparameters. random_state is fixed so the anomaly
#: ranking is byte-identical between runs.
IFOREST_N_ESTIMATORS = _env_int("FINGUARD_IFOREST_ESTIMATORS", 200)
IFOREST_CONTAMINATION = _env_float("FINGUARD_IFOREST_CONTAMINATION", 0.06)
IFOREST_RANDOM_STATE = SEED
IFOREST_MAX_SAMPLES = _env_int("FINGUARD_IFOREST_MAX_SAMPLES", 256)

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
# Investigator copilot (case narrative)
# --------------------------------------------------------------------------

#: How the case narrative is produced. Per DEMO-SPEC the default is the
#: deterministic template composer: it renders instantly, cannot fail live and
#: reads identically every run. An LLM may be layered on top when explicitly
#: enabled -- it only rewrites facts it is handed and never computes a score or
#: picks an action.
#:
#:   "none"      -> template composer only (default, stage-safe)
#:   "gemini"    -> Google Gemini via google-genai (GEMINI_API_KEY)
#:   "anthropic" -> Claude via the anthropic SDK (ANTHROPIC_API_KEY)
LLM_PROVIDER = os.environ.get("FINGUARD_LLM_PROVIDER", "none").strip().lower()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("FINGUARD_GEMINI_MODEL", "gemini-2.5-flash")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("FINGUARD_ANTHROPIC_MODEL", "claude-sonnet-5")

LLM_MAX_TOKENS = _env_int("FINGUARD_LLM_MAX_TOKENS", 700)

#: Where LLM narratives are cached so a live call never happens twice.
LLM_CACHE_DIR = Path(
    os.environ.get("FINGUARD_LLM_CACHE_DIR", str(BACKEND_DIR / "app" / "copilot" / "cache"))
)

# --------------------------------------------------------------------------
# API / serving
# --------------------------------------------------------------------------

API_HOST = os.environ.get("FINGUARD_HOST", "127.0.0.1")
API_PORT = _env_int("FINGUARD_PORT", 8000)

#: Comma-separated in the environment; a sensible dev default otherwise.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "FINGUARD_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if origin.strip()
]
