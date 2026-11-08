from __future__ import annotations

import sys
from typing import Any

from app.domain.models import Catalog, DownloadJob, Episode, Variant, safe_name
from app.domain.security import normalize_source_url
from app.adapters.outbound.downloader import FFmpegDownloaderAdapter, valid_video
from app.adapters.outbound.persistence import SqliteRepository
from app.adapters.outbound.system import WindowsSystemAdapter
from app.application.job_service import JobService
from app.ports.outbound.publisher import EventPublisherPort
from app.ports.outbound.source import MediaSourcePort
from app.sources.registry import resolve_episode as _default_resolve_episode

resolve_episode = _default_resolve_episode


class _DelegateSource(MediaSourcePort):
    def can_handle(self, url: str) -> bool:
        return True

    async def discover(self, url: str):
        raise NotImplementedError

    async def resolve(self, episode: Episode, page_url: str) -> list[Variant]:
        fn = getattr(sys.modules[__name__], "resolve_episode", _default_resolve_episode)
        from app.adapters.outbound.sources.http import SourceHttp
        http = SourceHttp()
        try:
            try:
                site = normalize_source_url(page_url).site
            except Exception:
                site = "UAKINO"
            return await fn(http, site, episode, page_url)
        finally:
            await http.close()


class _FuncPublisher(EventPublisherPort):
    def __init__(self, notify: Any) -> None:
        self.notify = notify

    async def publish(self, event: dict) -> None:
        if self.notify:
            res = self.notify(event)
            if hasattr(res, "__await__"):
                await res


class JobManager:
    def __init__(self, store: SqliteRepository, notify: Any) -> None:
        self.store = store
        self.notify = notify
        self._publisher = _FuncPublisher(notify)
        self._downloader = FFmpegDownloaderAdapter()
        self._system = WindowsSystemAdapter()
        self._source = _DelegateSource()
        self._service = JobService(
            repository=store,
            downloader=self._downloader,
            source=self._source,
            system=self._system,
            publisher=self._publisher,
        )

    @property
    def tasks(self) -> dict:
        return self._service.tasks

    @property
    def cancelled(self) -> set:
        return self._service.cancelled

    def create(
        self,
        scan_id: str,
        catalog: Catalog,
        episode_ids: list[str],
        quality: str,
        output_dir: str,
        parallel_limit: int,
    ) -> DownloadJob:
        return self._service.create_job_from_catalog(
            scan_id,
            catalog,
            episode_ids,
            quality,
            output_dir,
            parallel_limit,
        )

    async def cancel(self, job_id: str) -> DownloadJob:
        return await self._service.cancel_job(job_id)

    async def retry(self, job_id: str) -> DownloadJob:
        return await self._service.retry_job(job_id)

    async def delete_file(self, job_id: str, episode_id: str) -> DownloadJob:
        return await self._service.delete_file(job_id, episode_id)

    async def delete(self, job_id: str, delete_files: bool = False) -> None:
        await self._service.delete_job(job_id, delete_files=delete_files)


__all__ = ["JobManager", "resolve_episode", "safe_name", "valid_video"]
