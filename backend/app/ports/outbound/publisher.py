from __future__ import annotations

from abc import ABC, abstractmethod


class EventPublisherPort(ABC):
    @abstractmethod
    async def publish(self, event: dict) -> None:
        """Broadcast event to subscribers."""
