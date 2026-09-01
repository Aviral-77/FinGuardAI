"""FinGuard AI backend.

Run with::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .analysis import cached_analysis
from .api.live import router as live_router
from .api.live import ws_router as live_ws_router
from .api.routes import router as api_router
from .api.ws import router as ws_router
from .config import CORS_ORIGINS
from .live.state import LIVE

logger = logging.getLogger("finguard")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the analysis before serving.

    The Isolation Forest fit and the rule pass together take a second or two.
    Paying that at boot rather than on the first request keeps the demo's first
    click instant, and surfaces a broken dataset at startup instead of halfway
    through the presentation.
    """
    analysis = cached_analysis(True)
    cached_analysis(False)  # the rules-only variant behind the proof toggle
    logger.info(
        "analysis ready: %d accounts, %d transactions, %d flagged, %d networks (%d missed)",
        len(analysis.dataset.accounts),
        len(analysis.dataset.transactions),
        len(analysis.flagged_accounts),
        len(analysis.networks),
        len(analysis.missed_networks),
    )
    # Warm the live demo state too, so the first trigger on stage is instant.
    LIVE.reset()
    logger.info("live demo state ready at Beat 0")
    yield


app = FastAPI(
    title="FinGuard AI",
    description=(
        "Fraud detection console for retail banking. A deterministic graph + "
        "rule engine with a template-composed investigator copilot, driven live "
        "over an API. An optional anomaly layer and LLM narrative sit behind "
        "config flags."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(live_router)  # the DEMO-SPEC live API
app.include_router(live_ws_router)  # /ws/live
app.include_router(api_router)  # batch/replay analysis (additive)
app.include_router(ws_router)  # /ws/replay


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "FinGuard AI",
        "docs": "/docs",
        "health": "/api/health",
        "live_ws": "/ws/live",
        "replay_ws": "/ws/replay",
    }
