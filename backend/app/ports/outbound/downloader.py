from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from pathlib import Path

ProgressReporter = Callable[[float, int, str], Awaitable[None]]


class VideoDownloaderPort(ABC):
    @abstractmethod
    def has_required_tools(self) -> bool:
        """Check if FFmpeg and ffprobe are available in system."""

    @abstractmethod
    async def verify_video(self, path: Path, expected_duration: float) -> bool:
        """Validate downloaded video file structure and duration."""

    @abstractmethod
    async def download_stream(
        self,
        job_id: str,
        episode_id: str,
        playlist_url: str,
        referer: str,
        output_file: Path,
        duration: float,
        on_progress: ProgressReporter | None = None,
    ) -> None:
        """Download HLS stream to an MP4 destination file."""

    @abstractmethod
    def cancel_download(self, job_id: str, episode_id: str | None = None) -> None:
        """Terminate ongoing download process(es) for the job or episode."""
