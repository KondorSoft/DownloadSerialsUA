from __future__ import annotations

from app.ports.inbound.folder import FolderUseCase
from app.ports.outbound.repository import SettingsRepository
from app.ports.outbound.system import SystemPort


class FolderService(FolderUseCase):
    def __init__(self, settings: SettingsRepository, system: SystemPort) -> None:
        self.settings = settings
        self.system = system

    def get_downloads_folder(self) -> str:
        saved = self.settings.get_setting("output_dir")
        return saved or self.system.default_downloads_folder()

    def set_downloads_folder(self, path: str) -> str:
        clean = path.strip()
        self.settings.set_setting("output_dir", clean)
        return clean

    async def open_folder_picker(self, current_path: str) -> str:
        selected = await self.system.open_folder_dialog(current_path)
        if selected:
            self.settings.set_setting("output_dir", selected)
        return selected
