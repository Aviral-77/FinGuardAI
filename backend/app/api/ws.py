"""WebSocket replay.

The client opens ``/ws/replay`` and drives it with small JSON commands:

``{"cmd": "start", "speed": 40, "graph_enabled": true}``
``{"cmd": "pause"}`` / ``{"cmd": "resume"}`` / ``{"cmd": "stop"}``
``{"cmd": "speed", "speed": 120}``
``{"cmd": "step"}``   -- emit one event, for walking through the climax slowly

``speed`` is a compression factor: dataset hours per real second. The 30-day
window is far too long to watch, and a fixed delay per event would race through
the quiet stretches and then crawl through the ring. Compressing the *clock*
keeps the relative rhythm -- the pause before the ring assembles is still a
pause -- while fitting the window into a three-minute demo.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..analysis import cached_analysis
from ..replay.engine import ReplayEvent, build_events

router = APIRouter()

DEFAULT_SPEED_HOURS_PER_SECOND = 60.0
#: Never wait longer than this between events, however quiet the window is.
MAX_GAP_SECONDS = 1.5
#: Nor faster than this, or the feed is unreadable.
MIN_GAP_SECONDS = 0.02


class ReplaySession:
    """Per-connection replay state."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.events: list[ReplayEvent] = []
        self.index = 0
        self.speed = DEFAULT_SPEED_HOURS_PER_SECOND
        self.paused = False
        self.running = False
        self.graph_enabled = True

    def load(self, *, graph_enabled: bool) -> None:
        self.graph_enabled = graph_enabled
        self.events = build_events(cached_analysis(graph_enabled))
        self.index = 0

    def gap_to_next(self) -> float:
        """Real seconds to wait before the next event."""
        if self.index <= 0 or self.index >= len(self.events):
            return MIN_GAP_SECONDS
        delta = self.events[self.index].at - self.events[self.index - 1].at
        hours = delta.total_seconds() / 3600.0
        return max(MIN_GAP_SECONDS, min(MAX_GAP_SECONDS, hours / max(self.speed, 1e-6)))

    async def emit_one(self) -> bool:
        if self.index >= len(self.events):
            return False
        event = self.events[self.index]
        self.index += 1
        await self.websocket.send_json(event.to_dict())
        return True


async def _run(session: ReplaySession) -> None:
    """Pump events until the stream ends or the socket closes."""
    while session.running and session.index < len(session.events):
        if session.paused:
            await asyncio.sleep(0.1)
            continue
        await asyncio.sleep(session.gap_to_next())
        if not await session.emit_one():
            break
    session.running = False


@router.websocket("/ws/replay")
async def replay(websocket: WebSocket) -> None:
    await websocket.accept()
    session = ReplaySession(websocket)
    pump: asyncio.Task | None = None

    async def stop_pump() -> None:
        nonlocal pump
        session.running = False
        if pump is not None:
            pump.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump
            pump = None

    try:
        while True:
            message: dict[str, Any] = await websocket.receive_json()
            command = message.get("cmd")

            if command == "start":
                await stop_pump()
                session.speed = float(message.get("speed", DEFAULT_SPEED_HOURS_PER_SECOND))
                session.load(graph_enabled=bool(message.get("graph_enabled", True)))
                session.paused = False
                session.running = True
                await websocket.send_json(
                    {
                        "kind": "ready",
                        "total_events": len(session.events),
                        "graph_enabled": session.graph_enabled,
                        "speed": session.speed,
                    }
                )
                pump = asyncio.create_task(_run(session))

            elif command == "pause":
                session.paused = True
                await websocket.send_json({"kind": "paused", "at_index": session.index})

            elif command == "resume":
                session.paused = False
                await websocket.send_json({"kind": "resumed", "at_index": session.index})

            elif command == "speed":
                session.speed = float(message.get("speed", DEFAULT_SPEED_HOURS_PER_SECOND))
                await websocket.send_json({"kind": "speed", "speed": session.speed})

            elif command == "step":
                # Stepping implies manual control, so pause first -- otherwise
                # the pump and the step race for the same index.
                session.paused = True
                if not session.events:
                    session.load(graph_enabled=session.graph_enabled)
                await session.emit_one()

            elif command == "stop":
                await stop_pump()
                await websocket.send_json({"kind": "stopped", "at_index": session.index})

            else:
                await websocket.send_json({"kind": "error", "detail": f"unknown cmd {command!r}"})

    except WebSocketDisconnect:
        pass
    finally:
        await stop_pump()
