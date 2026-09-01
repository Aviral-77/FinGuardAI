"""The DEMO-SPEC API: presenter-driven live scoring.

Small and demo-friendly, exactly as the spec asks. Every mutating endpoint
returns the updated state and also broadcasts an event over ``/ws/live`` so the
canvas reacts without polling. This router is additive -- the batch/replay
endpoints from the earlier build still exist alongside it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from pydantic import BaseModel, Field

from ..live import scenario
from ..live.state import LIVE, FrozenAccountError
from ..report.pdf import build_report_pdf

router = APIRouter(prefix="/api")
ws_router = APIRouter()


# --------------------------------------------------------------------------
# WebSocket hub
# --------------------------------------------------------------------------


class Hub:
    """Fan-out of live events to every connected canvas."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


hub = Hub()

#: Tracks whether the ring banner has already been announced, so it fires once.
_ring_announced = {"value": False}


async def _announce_ring_if_new() -> None:
    ring = LIVE.ring()
    if ring and not _ring_announced["value"]:
        _ring_announced["value"] = True
        await hub.broadcast({"kind": "ring_detected", **ring})


# --------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------


class TransactionIn(BaseModel):
    from_account: str
    to_account: str
    amount: float
    channel: str = "IMPS"
    device_id: str | None = None
    timestamp: str | None = None


class BatchIn(BaseModel):
    transactions: list[TransactionIn]
    stagger_ms: int = Field(default=400, ge=0, le=5000)


# --------------------------------------------------------------------------
# Core transaction endpoints
# --------------------------------------------------------------------------


def _parse_timestamp(raw: str | None) -> "dt.datetime | None":
    """Parse an ISO timestamp, tolerating omitted or placeholder values.

    The DEMO-SPEC documents timestamp as "auto if omitted", and Swagger's
    /docs sends the literal example "string" -- neither is a real timestamp, so
    an unparseable value is treated as omitted (auto-assigned) rather than
    raising a 500.
    """
    import datetime as dt

    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw)
    except ValueError:
        return None


async def _apply(txn: TransactionIn) -> dict[str, Any]:
    """Inject one transaction, broadcast, return the API payload."""
    when = _parse_timestamp(txn.timestamp)
    result = LIVE.inject(
        from_account=txn.from_account,
        to_account=txn.to_account,
        amount=txn.amount,
        channel=txn.channel,
        timestamp=when,
        device_id=txn.device_id,
    )
    await hub.broadcast(
        {
            "kind": "transaction",
            "transaction_id": result.transaction_id,
            "from_account": result.from_account,
            "to_account": result.to_account,
            "amount": result.amount,
            "timestamp": result.timestamp,
            "channel": txn.channel,
        }
    )
    if result.scores_updated:
        await hub.broadcast({"kind": "score_update", "nodes": result.scores_updated})
    await _announce_ring_if_new()
    return {
        "transaction_id": result.transaction_id,
        "accepted": True,
        "scores_updated": result.scores_updated,
    }


@router.post("/transaction")
async def post_transaction(txn: TransactionIn):
    try:
        return await _apply(txn)
    except FrozenAccountError as exc:
        await hub.broadcast(
            {
                "kind": "rejected",
                "from_account": txn.from_account,
                "to_account": txn.to_account,
                "reason": str(exc),
            }
        )
        return JSONResponse(
            status_code=409,
            content={"accepted": False, "reason": str(exc)},
        )


@router.post("/transaction/batch")
async def post_batch(batch: BatchIn):
    """Inject in sequence with a delay so the fan-out animates.

    Frozen-account rejections inside a batch are reported per-item rather than
    aborting the whole batch -- a presenter firing a post-freeze batch should
    still see each attempt bounce.
    """
    results: list[dict[str, Any]] = []
    for txn in batch.transactions:
        try:
            results.append(await _apply(txn))
        except FrozenAccountError as exc:
            await hub.broadcast(
                {
                    "kind": "rejected",
                    "from_account": txn.from_account,
                    "to_account": txn.to_account,
                    "reason": str(exc),
                }
            )
            results.append({"accepted": False, "reason": str(exc)})
        if batch.stagger_ms:
            await asyncio.sleep(batch.stagger_ms / 1000.0)
    return {"count": len(results), "results": results}


# --------------------------------------------------------------------------
# Account actions
# --------------------------------------------------------------------------


@router.post("/account/{account_id}/freeze")
async def freeze(account_id: str):
    view = LIVE.freeze(account_id)
    await hub.broadcast({"kind": "frozen", "account_id": account_id})
    return {"account_id": account_id, "frozen": True, "account": view}


@router.post("/account/{account_id}/report")
async def file_report(account_id: str):
    view = LIVE.file_report(account_id)
    await hub.broadcast({"kind": "reported", "account_id": account_id})
    return {"account_id": account_id, "reported": True, "account": view}


@router.get("/account/{account_id}/report.pdf")
def account_report_pdf(account_id: str):
    case = LIVE.account_view(account_id)
    pdf = build_report_pdf(case, LIVE.analysis, ring=LIVE.ring())
    filename = f"finguard-case-{account_id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/account/{account_id}")
def account(account_id: str):
    return LIVE.account_view(account_id)


# --------------------------------------------------------------------------
# State + demo control
# --------------------------------------------------------------------------


@router.get("/state")
def state():
    return LIVE.snapshot()


@router.post("/demo/reset")
async def reset():
    LIVE.reset()
    _ring_announced["value"] = False
    await hub.broadcast({"kind": "reset"})
    return {"reset": True, **LIVE.snapshot()}


@router.post("/demo/beat/{number}")
async def fire_beat(number: int, stagger_ms: int = 400):
    """Preset trigger: fire a scripted beat as a staggered batch.

    So the presenter (or the control strip) never types JSON. Beat 1 is the
    victim's transfers; Beat 2 is the fan-out.
    """
    if number == 1:
        beats = scenario.beat_one()
    elif number == 2:
        beats = scenario.beat_two()
    else:
        return JSONResponse(status_code=404, content={"error": f"no beat {number}"})
    batch = BatchIn(
        transactions=[TransactionIn(**b.to_payload()) for b in beats],
        stagger_ms=stagger_ms,
    )
    return await post_batch(batch)


@router.post("/demo/blocked-attempt")
async def blocked_attempt():
    """Fire the post-freeze bounce: a transfer into the frozen Account A."""
    txn = TransactionIn(**scenario.blocked_attempt().to_payload())
    return await post_transaction(txn)


# --------------------------------------------------------------------------
# WebSocket
# --------------------------------------------------------------------------


@ws_router.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        # Send the current canvas immediately so a late joiner is in sync.
        await ws.send_json({"kind": "snapshot", **LIVE.snapshot()})
        while True:
            # We do not expect client messages, but receiving keeps the socket
            # alive and lets us notice a disconnect promptly.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(ws)
