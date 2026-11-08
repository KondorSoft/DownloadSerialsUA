from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.models import DownloadJob


class JobManagementUseCase(ABC):
    @abstractmethod
    def create_job(
        self,
        scan_id: str,
        episode_ids: list[str],
        quality: str,
        output_dir: str,
        parallel_limit: int,
    ) -> DownloadJob:
        """Create and start a new download job."""

    @abstractmethod
    async def cancel_job(self, job_id: str) -> DownloadJob:
        """Cancel a running or queued download job."""

    @abstractmethod
    async def retry_job(self, job_id: str) -> DownloadJob:
        """Retry failed or cancelled episodes in a job."""

    @abstractmethod
    async def delete_file(self, job_id: str, episode_id: str) -> DownloadJob:
        """Delete an individual downloaded episode file from disk."""

    @abstractmethod
    async def delete_job(self, job_id: str, delete_files: bool = False) -> None:
        """Delete a download job and optionally all its downloaded files."""

    @abstractmethod
    def get_job(self, job_id: str) -> DownloadJob | None:
        """Get job by ID."""

    @abstractmethod
    def list_jobs(self) -> list[DownloadJob]:
        """List recent jobs."""
