from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class SystemPort(ABC):
    @abstractmethod
    def default_downloads_folder(self) -> str:
        """Resolve system default downloads folder."""

    @abstractmethod
    def get_free_disk_space(self, path: Path) -> int:
        """Get available disk space in bytes for path."""

    @abstractmethod
    async def open_folder_dialog(self, initial_path: str) -> str:
        """Open native system folder browser dialog."""
