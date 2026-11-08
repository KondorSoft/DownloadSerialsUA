from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.application.folder_service import FolderService
from app.application.job_service import JobService
from app.application.scan_service import ScanService
from app.domain.models import Catalog, DownloadJob, Episode, EpisodeProgress, ScanState, Variant, safe_name
from app.domain.security import normalize_source_url, validate_url
from app.ports.outbound.downloader import VideoDownloaderPort
from app.ports.outbound.publisher import EventPublisherPort
from app.ports.outbound.repository import JobRepository, SettingsRepository
from app.ports.outbound.source import MediaSourcePort
from app.ports.outbound.system import SystemPort


# --- Test Fakes & In-Memory Adapters for Hexagonal Ports ---

class InMemoryJobRepository(JobRepository, SettingsRepository):
    def __init__(self) -> None:
        self.jobs: dict[str, DownloadJob] = {}
        self.scans: dict[str, ScanState] = {}
        self.settings: dict[str, str] = {}
        self.interrupted_called = False

    def save_job(self, job: DownloadJob) -> None:
        self.jobs[job.id] = job.model_copy(deep=True)

    def get_job(self, job_id: str) -> DownloadJob | None:
        job = self.jobs.get(job_id)
        return job.model_copy(deep=True) if job else None

    def delete_job(self, job_id: str) -> bool:
        return self.jobs.pop(job_id, None) is not None

    def list_jobs(self, limit: int = 30) -> list[DownloadJob]:
        return [j.model_copy(deep=True) for j in list(self.jobs.values())[:limit]]

    def save_scan(self, scan: ScanState) -> None:
        self.scans[scan.id] = scan.model_copy(deep=True)

    def get_scan(self, scan_id: str) -> ScanState | None:
        scan = self.scans.get(scan_id)
        return scan.model_copy(deep=True) if scan else None

    def mark_interrupted(self) -> None:
        self.interrupted_called = True

    def get_setting(self, key: str) -> str | None:
        return self.settings.get(key)

    def set_setting(self, key: str, value: str) -> None:
        self.settings[key] = value


class FakeMediaSource(MediaSourcePort):
    def __init__(self, episodes: list[Episode] | None = None) -> None:
        self.episodes = episodes or []

    def can_handle(self, url: str) -> bool:
        return "uakino" in url or "uaflix" in url

    async def discover(self, url: str) -> tuple[str, int | None, list[Episode]]:
        return "Тестовий Серіал", 1, self.episodes

    async def resolve(self, episode: Episode, page_url: str) -> list[Variant]:
        return episode.variants


class FakeDownloader(VideoDownloaderPort):
    def __init__(self, tools_available: bool = True) -> None:
        self.tools_available = tools_available
        self.downloads: list[tuple[str, str, Path]] = []
        self.cancelled_jobs: set[str] = set()

    def has_required_tools(self) -> bool:
        return self.tools_available

    async def verify_video(self, path: Path, expected_duration: float) -> bool:
        return path.exists() and path.stat().st_size > 0

    async def download_stream(
        self,
        job_id: str,
        episode_id: str,
        playlist_url: str,
        referer: str,
        output_file: Path,
        duration: float,
        on_progress=None,
    ) -> None:
        self.downloads.append((job_id, episode_id, output_file))
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(b"mock_video_bytes")
        if on_progress:
            await on_progress(100.0, 16, "5MB/s")

    def cancel_download(self, job_id: str, episode_id: str | None = None) -> None:
        self.cancelled_jobs.add(job_id)


class FakeSystem(SystemPort):
    def __init__(self, free_space: int = 100_000_000_000) -> None:
        self.free_space = free_space
        self.dialog_path = "/custom/path"

    def default_downloads_folder(self) -> str:
        return "/default/downloads"

    def get_free_disk_space(self, path: Path) -> int:
        return self.free_space

    async def open_folder_dialog(self, initial_path: str) -> str:
        return self.dialog_path


class FakePublisher(EventPublisherPort):
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(self, event: dict) -> None:
        self.events.append(event)


# --- Hexagonal Architecture Tests ---

def test_domain_safe_name_and_best_variant():
    assert safe_name("Серіал: Сезон 1 / Епізод 1?*") == "Серіал_ Сезон 1 _ Епізод 1__"

    v1 = Variant(label="720p", width=1280, height=720, bandwidth=1000, duration_seconds=10,
                 estimated_bytes=1000, playlist_url="url1", referer="ref")
    v2 = Variant(label="1080p", width=1920, height=1080, bandwidth=2000, duration_seconds=10,
                 estimated_bytes=2000, playlist_url="url2", referer="ref")
    ep = Episode(id="ep1", number=1, season=1, source_url="url", variants=[v1, v2])

    assert ep.best_variant() == v2


def test_folder_service_use_case():
    repo = InMemoryJobRepository()
    system = FakeSystem()
    service = FolderService(settings=repo, system=system)

    # Initially returns system default
    assert service.get_downloads_folder() == "/default/downloads"

    # Setting saves and updates
    service.set_downloads_folder("D:\\CustomDownloads")
    assert service.get_downloads_folder() == "D:\\CustomDownloads"

    # Dialog updates setting
    selected = asyncio.run(service.open_folder_picker("D:\\CustomDownloads"))
    assert selected == "/custom/path"
    assert service.get_downloads_folder() == "/custom/path"


def test_job_service_use_case_with_max_quality(tmp_path):
    async def run_scenario():
        repo = InMemoryJobRepository()
        downloader = FakeDownloader()
        system = FakeSystem()
        publisher = FakePublisher()

        v1080 = Variant(label="1080p", width=1920, height=1080, bandwidth=2000, duration_seconds=5,
                        estimated_bytes=2000, playlist_url="url1080", referer="ref")
        v720 = Variant(label="720p", width=1280, height=720, bandwidth=1000, duration_seconds=5,
                       estimated_bytes=1000, playlist_url="url720", referer="ref")

        ep1 = Episode(id="ep1", number=1, season=1, source_url="url1", variants=[v1080, v720])
        ep2 = Episode(id="ep2", number=2, season=1, source_url="url2", variants=[v720])

        catalog = Catalog(id="cat1", source_url="https://uakino.best/series.html", site="UAKINO",
                          title="Супер Серіал", season=1, episodes=[ep1, ep2])

        scan = ScanState(id="scan1", status="complete", catalog=catalog)
        repo.save_scan(scan)

        source = FakeMediaSource(episodes=[ep1, ep2])
        job_service = JobService(
            repository=repo,
            downloader=downloader,
            source=source,
            system=system,
            publisher=publisher,
        )

        out_dir = tmp_path / "downloads"
        out_dir.mkdir()

        job = job_service.create_job(
            scan_id="scan1",
            episode_ids=["ep1", "ep2"],
            quality="max",
            output_dir=str(out_dir),
            parallel_limit=2,
        )

        assert job.quality == "max"
        assert job.resolution == "Різна роздільність"
        assert job.estimated_bytes == 3000
        assert len(job.episodes) == 2

        # Wait for background mock download to finish
        assert job.id in job_service.tasks
        await asyncio.wait_for(job_service.tasks[job.id], 5)

        finished = repo.get_job(job.id)
        assert finished.status == "complete"
        assert len(downloader.downloads) == 2

        # Delete job
        await job_service.delete_job(job.id, delete_files=False)
        assert repo.get_job(job.id) is None
        assert any(e.get("type") == "job_deleted" for e in publisher.events)

    asyncio.run(run_scenario())
