"""One authenticated WebSocket per browser tab, used only for server -> client pushes.

    open /ws  ->  Origin must be an allowed frontend origin   (else close 4403)
    client sends {"type": "auth", "token": "<jwt>"} within 10 s (else close 4408)
    token checked with the same JWT logic as HTTP              (else close 4401)
    server replies {"type": "ready"} and registers the socket
    the socket is closed with 4401 when the token expires
"""
import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.realtime import manager
from app.core.security import decode_token
from app.models.user import User

router = APIRouter(tags=["Realtime"])
logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403
CLOSE_AUTH_TIMEOUT = 4408


def user_exists(user_id: int) -> bool:
    # a short session just for the lookup; nothing is held open per connection
    with SessionLocal() as db:
        return db.get(User, user_id) is not None


async def authenticate(ws: WebSocket) -> tuple[int, float] | None:
    """(user_id, token expiry timestamp), or None after closing the socket."""
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await ws.close(code=CLOSE_AUTH_TIMEOUT)
        return None

    try:
        message = json.loads(raw)
        token = message["token"] if message.get("type") == "auth" else None
    except (ValueError, TypeError, KeyError, AttributeError):
        token = None

    payload = decode_token(token) if isinstance(token, str) else None
    try:
        user_id = int(payload["sub"]) if payload else None
    except (KeyError, TypeError, ValueError):
        user_id = None

    if user_id is None or not await run_in_threadpool(user_exists, user_id):
        await ws.close(code=CLOSE_UNAUTHORIZED)
        return None
    return user_id, float(payload["exp"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()  # accept first so the browser receives our close codes

    # another site's page must not be able to open a socket from a victim's browser
    if ws.headers.get("origin") not in settings.cors_origins_list:
        await ws.close(code=CLOSE_FORBIDDEN_ORIGIN)
        return

    auth = await authenticate(ws)
    if auth is None:
        return
    user_id, expires_at = auth

    manager.connect(user_id, ws)
    try:
        await ws.send_json({"type": "ready"})
        while True:
            remaining = expires_at - time.time()
            if remaining <= 0:
                await ws.close(code=CLOSE_UNAUTHORIZED)  # token expired
                break
            try:
                # clients have nothing to send after auth; this just waits for
                # disconnect (uvicorn's ping detects dead connections) or expiry
                await asyncio.wait_for(ws.receive_text(), timeout=remaining)
            except asyncio.TimeoutError:
                continue  # loop re-checks expiry and closes
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, ws)
