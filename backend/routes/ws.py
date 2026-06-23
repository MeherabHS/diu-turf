"""WebSocket route — real-time booking broadcast (PostgreSQL auth)."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from services.jwt_util import decode_token
from services.ws_manager import ws_manager

router = APIRouter(tags=["ws"])
log = logging.getLogger(__name__)


@router.websocket("/api/ws/bookings")
async def bookings_ws(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    """Authenticate via JWT, then stream booking mutation events."""
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id_str = payload.get("sub", "")
    if not user_id_str:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify the user exists in PostgreSQL.
    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    pool = websocket.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, is_active FROM users WHERE id = $1", user_uuid
        )
    if not row or not row["is_active"]:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({"type": "hello", "user_id": user_id_str})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)
