from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import DownloadJob, ScanState


class JobRepository(ABC):
    @abstractmethod
    def save_job(self, job: DownloadJob) -> None:
        """Save or update download job."""

    @abstractmethod
    def get_job(self, job_id: str) -> DownloadJob | None:
        """Retrieve download job by ID."""

    @abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Delete download job by ID. Returns True if deleted."""

    @abstractmethod
    def list_jobs(self, limit: int = 30) -> list[DownloadJob]:
        """List recent download jobs."""

    @abstractmethod
    def save_scan(self, scan: ScanState) -> None:
        """Save or update scan state."""

    @abstractmethod
    def get_scan(self, scan_id: str) -> ScanState | None:
        """Retrieve scan state by ID."""

    @abstractmethod
    def mark_interrupted(self) -> None:
        """Mark unfinished jobs as interrupted on startup."""


class SettingsRepository(ABC):
    @abstractmethod
    def get_setting(self, key: str) -> str | None:
        """Get persisted setting value."""

    @abstractmethod
    def set_setting(self, key: str, value: str) -> None:
        """Persist setting value."""
