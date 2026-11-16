"""WebSockets: control/event stream ``/ws`` (§5.3) and binary video ``/ws/video`` (§5.4).

Video runs on its own socket so video congestion never delays an e-stop or an alert. Owner events
come from the hardware thread and are handed to the event loop with ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from hibiscus_station.api.security import COOKIE, WS_PROTOCOL, LocalAuth
from hibiscus_station.errors import StationError
from hibiscus_station.hw.cameras import VideoClient
from hibiscus_station.programs.schemas import OperatorInput
from hibiscus_station.station import Station

log = logging.getLogger(__name__)
QUEUE_MAX = 512
DROPPABLE = {"joints", "telemetry", "calibration"}


class EventHub:
    """Fan-out of owner events to every control-socket client (bounded queues)."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: set[asyncio.Queue[dict[str, Any]]] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def publish(self, kind: str, payload: dict[str, Any]) -> None:
        loop = self.loop
        if loop is None or not self.clients:
            return
        msg = {**payload, "type": kind}
        try:
            loop.call_soon_threadsafe(self._put, msg)
        except RuntimeError:  # loop closed during shutdown
            pass

    def _put(self, msg: dict[str, Any]) -> None:
        for q in list(self.clients):
            if q.full():
                if msg["type"] in DROPPABLE:
                    continue
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait(msg)


def _authorized(ws: WebSocket, auth: LocalAuth) -> tuple[bool, str | None]:
    if not auth.host_ok(ws.headers.get("host")):
        return False, None
    if not auth.origin_ok(ws.headers.get("origin")):
        return False, None
    if auth.cookie_ok(ws.cookies.get(COOKIE)):
        return True, None
    protocols = [p.strip() for p in ws.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
    tok = auth.ws_protocol_token(protocols)
    if tok is not None and auth.token_ok(tok) and WS_PROTOCOL in protocols:
        return True, WS_PROTOCOL
    if auth.bearer_ok(ws.headers.get("authorization")):
        return True, None
    return False, None


def build_ws_router(hub: EventHub) -> APIRouter:
    r = APIRouter(prefix="/api/v1")  # spec §5.2: /api/v1/ws and /api/v1/ws/video

    @r.websocket("/ws")
    async def control(ws: WebSocket) -> None:
        st: Station = ws.app.state.station
        auth: LocalAuth = ws.app.state.auth
        ok, subprotocol = _authorized(ws, auth)
        if not ok:
            await ws.close(code=4401)
            return
        await ws.accept(subprotocol=subprotocol)
        hub.bind(asyncio.get_running_loop())
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAX)
        await ws.send_json({"type": "hello", "v": 1, "status": st.status()})
        try:
            first = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        except (TimeoutError, WebSocketDisconnect, json.JSONDecodeError, KeyError):
            with contextlib.suppress(Exception):
                await ws.close(code=4401)
            return
        if not isinstance(first, dict) or first.get("type") != "hello":
            await ws.close(code=4401)
            return
        heartbeat = bool(first.get("heartbeat", False))
        hub.clients.add(q)

        async def sender() -> None:
            while True:
                msg = await q.get()
                await ws.send_json(msg)

        task = asyncio.create_task(sender())
        try:
            while True:
                msg = await ws.receive_json()
                if not isinstance(msg, dict):
                    continue
                kind = msg.get("type")
                if kind == "estop":
                    st.owner.press_estop("user", relax=bool(msg.get("relax", False)))
                elif kind == "heartbeat":
                    if heartbeat:
                        st.owner.heartbeat()
                elif kind == "control":
                    action = str(msg.get("action", ""))
                    try:
                        await asyncio.to_thread(st.owner.call, "control", action=action, timeout=60.0)
                    except Exception as exc:  # reported to this client only
                        await ws.send_json({"type": "error", "action": action, "detail": str(exc)[:300]})
                elif kind == "ping":
                    await ws.send_json({"type": "pong"})
                elif kind == "program_input":
                    # station-programs.md §4 operator input -> the current run's ProgramRuntime.input
                    try:
                        ev = OperatorInput.model_validate({k: v for k, v in msg.items() if k != "type"})
                        await asyncio.to_thread(st.programs.runs.deliver, ev)
                    except (ValidationError, StationError) as exc:
                        detail = exc.detail if isinstance(exc, StationError) else "bad program_input"
                        await ws.send_json(
                            {"type": "error", "action": "program_input", "detail": detail[:300]}
                        )
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.clients.discard(q)
            task.cancel()
            with contextlib.suppress(BaseException):
                await task

    @r.websocket("/ws/video")
    async def video(ws: WebSocket) -> None:
        st: Station = ws.app.state.station
        auth: LocalAuth = ws.app.state.auth
        ok, subprotocol = _authorized(ws, auth)
        if not ok:
            await ws.close(code=4401)
            return
        await ws.accept(subprotocol=subprotocol)
        client = VideoClient(asyncio.get_running_loop())
        st.encoder.add(client)

        async def receiver() -> None:
            while True:
                msg = await ws.receive_json()
                if isinstance(msg, dict) and msg.get("type") == "subscribe":
                    cams = [str(c) for c in msg.get("cameras", [])]
                    client.subscribe(
                        cams,
                        int(msg.get("width", st.settings.preview.width)),
                        float(msg.get("fps", st.settings.preview.fps)),
                    )

        rtask = asyncio.create_task(receiver())
        try:
            while not rtask.done():
                if client.event is None:
                    break
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(client.event.wait(), timeout=0.5)
                client.event.clear()
                frames, errors = client.take()
                for cam, code in errors.items():
                    await ws.send_json({"type": "camera_error", "cam": cam, "code": code})
                for data in frames.values():
                    await ws.send_bytes(data)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            st.encoder.remove(client)
            rtask.cancel()
            with contextlib.suppress(BaseException):
                await rtask

    return r
