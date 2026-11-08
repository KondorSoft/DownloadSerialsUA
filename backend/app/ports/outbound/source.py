from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import Episode, Variant


class MediaSourcePort(ABC):
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this source handler supports the given URL."""

    @abstractmethod
    async def discover(self, url: str) -> tuple[str, int | None, list[Episode]]:
        """Extract title, season number and episode list from source page."""

    @abstractmethod
    async def resolve(self, episode: Episode, page_url: str) -> list[Variant]:
        """Resolve available video variants (streams) for the episode."""
