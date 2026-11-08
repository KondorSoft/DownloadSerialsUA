from __future__ import annotations

from fastapi import WebSocket

from app.ports.outbound.publisher import EventPublisherPort


class WebSocketEventPublisher(EventPublisherPort):
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    def add_client(self, websocket: WebSocket) -> None:
        self.clients.add(websocket)

    def remove_client(self, websocket: WebSocket) -> None:
        self.clients.discard(websocket)

    async def publish(self, event: dict) -> None:
        for client in list(self.clients):
            try:
                await client.send_json(event)
            except Exception:
                self.clients.discard(client)
