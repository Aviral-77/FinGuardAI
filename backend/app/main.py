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
from .api.routes import router as api_router
from .api.ws import router as ws_router
from .config import CORS_ORIGINS

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
    yield


app = FastAPI(
    title="FinGuard AI",
    description=(
        "Fraud detection console for retail banking. Graph layer, deterministic "
        "rule engine, anomaly model and investigator copilot."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "FinGuard AI",
        "docs": "/docs",
        "health": "/api/health",
        "replay": "/ws/replay",
    }
