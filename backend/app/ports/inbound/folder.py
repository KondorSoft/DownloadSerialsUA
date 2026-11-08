from __future__ import annotations

from abc import ABC, abstractmethod


class FolderUseCase(ABC):
    @abstractmethod
    def get_downloads_folder(self) -> str:
        """Get the configured or default downloads folder."""

    @abstractmethod
    def set_downloads_folder(self, path: str) -> str:
        """Persist user preferred downloads folder."""

    @abstractmethod
    async def open_folder_picker(self, current_path: str) -> str:
        """Open system folder selection dialog."""
