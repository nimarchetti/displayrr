"""webrr — web remote debug UI for the displayrr stack.

Taps the switchrr frame PUB socket, streams PNG frames over WebSocket,
and injects virtual hardware events (toggle switch, encoder) back into
switchrr's hardware event PULL socket.
"""

import asyncio
import io
import json
import os
import threading
import time
from contextlib import asynccontextmanager

import zmq
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from PIL import Image

FRAME_TAP_ADDRESS = os.environ["FRAME_TAP_ADDRESS"]
EVENT_ADDRESS = os.environ["SWITCHRR_EVENT_ADDRESS"]
HW_EVENT_ADDRESS = os.environ["SWITCHRR_HW_EVENT_ADDRESS"]

# Which display to tap — defaults to "default", overridable via env
WEBRR_DISPLAY_ID = os.environ.get("WEBRR_DISPLAY_ID", "default")


def _load_mode_registry() -> tuple[list[dict], str]:
    """Return (modes, default_mode_name) for WEBRR_DISPLAY_ID from DISPLAY_REGISTRY."""
    raw = os.environ.get("DISPLAY_REGISTRY", "").strip()
    if raw:
        try:
            registry = json.loads(raw)
            modes = []
            default_mode = ""
            for display in registry:
                if display.get("display_id") != WEBRR_DISPLAY_ID:
                    continue
                for idx, m in enumerate(display.get("modes", []), 1):
                    modes.append({
                        "mode_name": m.get("mode_name"),
                        "display_name": m.get("display_name", m.get("mode_name")),
                        "display_id": display.get("display_id"),
                        "toggle_position": idx,
                    })
                    if m.get("default") and not default_mode:
                        default_mode = m.get("mode_name", "")
            return modes, default_mode
        except (json.JSONDecodeError, TypeError):
            pass
    modes = json.loads(os.environ.get("MODE_REGISTRY", "[]"))
    default_mode = next((m["mode_name"] for m in modes if m.get("default")), "")
    return modes, default_mode


MODE_REGISTRY, _default_mode = _load_mode_registry()

# ---------------------------------------------------------------------------
# Shared state (threads → asyncio)
# ---------------------------------------------------------------------------

_latest_frame: bytes = b""
_latest_frame_lock = threading.Lock()

_active_mode: str = _default_mode
_active_mode_lock = threading.Lock()

_ws_clients: set[WebSocket] = set()
_ws_clients_lock: asyncio.Lock  # initialised in lifespan

_loop: asyncio.AbstractEventLoop  # set in lifespan

# ZMQ hardware event socket + lock (used from async REST endpoints via executor)
_hw_socket: zmq.Socket
_hw_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Background threads
# ---------------------------------------------------------------------------


def _frame_thread() -> None:
    """Subscribe to frame tap PUB; decode raw pixels; update _latest_frame."""
    global _latest_frame
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.connect(FRAME_TAP_ADDRESS)
    sock.setsockopt(zmq.SUBSCRIBE, b"")
    while True:
        try:
            parts = sock.recv_multipart()
        except zmq.ZMQError:
            break
        if len(parts) != 2:
            continue
        try:
            header = json.loads(parts[0])
            if header.get("display_id", WEBRR_DISPLAY_ID) != WEBRR_DISPLAY_ID:
                continue
            w, h = header["width"], header["height"]
            pil_mode = "RGB" if header.get("pixel_format", "RGB24") == "RGB24" else "L"
            img = Image.frombytes(pil_mode, (w, h), parts[1])
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=False)
            png = buf.getvalue()
        except Exception:
            continue
        with _latest_frame_lock:
            _latest_frame = png


def _event_thread() -> None:
    """Subscribe to mode events PUB; track active mode; broadcast to WS clients."""
    global _active_mode
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.connect(EVENT_ADDRESS)
    sock.setsockopt(zmq.SUBSCRIBE, b"")
    while True:
        try:
            raw = sock.recv()
        except zmq.ZMQError:
            break
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if msg.get("display_id", WEBRR_DISPLAY_ID) != WEBRR_DISPLAY_ID:
            continue
        event = msg.get("event")
        if event == "MODE_ACTIVE":
            with _active_mode_lock:
                _active_mode = msg.get("mode", "")
        if event in ("MODE_ACTIVE", "MODE_INACTIVE"):
            asyncio.run_coroutine_threadsafe(_broadcast_text(json.dumps(msg)), _loop)


# ---------------------------------------------------------------------------
# WebSocket broadcast helper
# ---------------------------------------------------------------------------


async def _broadcast_text(text: str) -> None:
    async with _ws_clients_lock:
        dead: set[WebSocket] = set()
        for ws in list(_ws_clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        _ws_clients.difference_update(dead)


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _hw_socket, _ws_clients_lock, _loop
    _loop = asyncio.get_running_loop()
    _ws_clients_lock = asyncio.Lock()

    ctx = zmq.Context.instance()
    _hw_socket = ctx.socket(zmq.PUSH)
    _hw_socket.connect(HW_EVENT_ADDRESS)

    threading.Thread(target=_frame_thread, daemon=True).start()
    threading.Thread(target=_event_thread, daemon=True).start()

    yield

    _hw_socket.close(linger=0)
    ctx.term()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    with open("/app/static/index.html") as f:
        return f.read()


@app.get("/embed", response_class=HTMLResponse)
async def embed() -> str:
    with open("/app/static/embed.html") as f:
        return f.read()


@app.get("/api/modes")
async def get_modes() -> dict:
    with _active_mode_lock:
        mode = _active_mode
    return {"modes": MODE_REGISTRY, "active_mode": mode}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    async with _ws_clients_lock:
        _ws_clients.add(websocket)
    try:
        with _active_mode_lock:
            mode = _active_mode
        await websocket.send_text(json.dumps({"event": "MODE_ACTIVE", "mode": mode}))
        last_sent: bytes = b""
        while True:
            with _latest_frame_lock:
                current = _latest_frame
            if current and current is not last_sent:
                await websocket.send_bytes(current)
                last_sent = current
            await asyncio.sleep(0.04)  # cap at ~25 fps
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _ws_clients_lock:
            _ws_clients.discard(websocket)


# ---------------------------------------------------------------------------
# Hardware event injection
# ---------------------------------------------------------------------------


def _send_hw_sync(event: dict) -> None:
    with _hw_lock:
        _hw_socket.send(json.dumps(event).encode())


async def _send_hw(event: dict) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_hw_sync, event)


@app.post("/event/toggle/{position}")
async def toggle(position: int) -> dict:
    await _send_hw({"event": "TOGGLE_SWITCH", "position": position, "timestamp_ms": _now_ms()})
    return {"ok": True}


@app.post("/event/encoder/delta/{delta}")
async def encoder_delta(delta: int) -> dict:
    await _send_hw({"event": "ENCODER_DELTA", "delta": delta, "timestamp_ms": _now_ms()})
    return {"ok": True}


@app.post("/event/encoder/push")
async def encoder_push() -> dict:
    await _send_hw({"event": "ENCODER_PUSH", "timestamp_ms": _now_ms()})
    return {"ok": True}


def _now_ms() -> int:
    return int(time.time() * 1000)
