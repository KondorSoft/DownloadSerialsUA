from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from app.domain.models import Catalog, ScanState

ProgressCallback = Callable[[int, int], Awaitable[None]]


class ScanUseCase(ABC):
    @abstractmethod
    async def start_scan(self, raw_url: str) -> ScanState:
        """Initiate background scan for a media catalog."""

    @abstractmethod
    def get_scan(self, scan_id: str) -> ScanState | None:
        """Retrieve scan status by ID."""
