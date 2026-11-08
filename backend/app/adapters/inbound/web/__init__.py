from __future__ import annotations

from app.adapters.inbound.web.api import create_api_router
from app.adapters.inbound.web.websocket import create_websocket_router

__all__ = ["create_api_router", "create_websocket_router"]
