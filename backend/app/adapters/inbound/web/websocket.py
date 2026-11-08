from __future__ import annotations

import secrets
from collections.abc import Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.adapters.outbound.publisher.event_publisher import WebSocketEventPublisher


def create_websocket_router(
    publisher: WebSocketEventPublisher,
    token_getter: Callable[[], str],
) -> APIRouter:
    router = APIRouter()

    @router.websocket("/api/events")
    async def events(websocket: WebSocket):
        client_token = websocket.query_params.get("token", "")
        if not secrets.compare_digest(client_token, token_getter()):
            await websocket.close(code=1008)
            return

        await websocket.accept()
        publisher.add_client(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            publisher.remove_client(websocket)

    return router
