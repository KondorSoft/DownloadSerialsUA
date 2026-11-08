from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from app.domain.models import Catalog, DownloadJob, Episode, EpisodeProgress, Variant, safe_name
from app.ports.inbound.jobs import JobManagementUseCase
from app.ports.outbound.downloader import VideoDownloaderPort
from app.ports.outbound.publisher import EventPublisherPort
from app.ports.outbound.repository import JobRepository
from app.ports.outbound.source import MediaSourcePort
from app.ports.outbound.system import SystemPort


class JobService(JobManagementUseCase):
    def __init__(
        self,
        repository: JobRepository,
        downloader: VideoDownloaderPort,
        source: MediaSourcePort,
        system: SystemPort,
        publisher: EventPublisherPort,
    ) -> None:
        self.repository = repository
        self.downloader = downloader
        self.source = source
        self.system = system
        self.publisher = publisher
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancelled: set[str] = set()

    def with_resolution(self, job: DownloadJob) -> DownloadJob:
        if job.resolution:
            return job
        scan = self.repository.get_scan(job.catalog_id)
        if not scan or not scan.catalog:
            return job
        selected = {episode.episode_id for episode in job.episodes}
        if job.quality in ("max", "MAX", "Максимальна"):
            dimensions = {
                (max(episode.variants, key=lambda v: (v.height, v.bandwidth)).width,
                 max(episode.variants, key=lambda v: (v.height, v.bandwidth)).height)
                for episode in scan.catalog.episodes
                if episode.id in selected and episode.variants
            }
            dimensions = {(w, h) for (w, h) in dimensions if w and h}
        else:
            dimensions = {(variant.width, variant.height) for episode in scan.catalog.episodes if episode.id in selected
                          for variant in episode.variants if variant.label == job.quality and variant.width and variant.height}
        if len(dimensions) == 1:
            width, height = next(iter(dimensions))
            job.resolution = f"{width} × {height}"
        elif dimensions:
            job.resolution = "Різна роздільність"
        return job

    def get_job(self, job_id: str) -> DownloadJob | None:
        job = self.repository.get_job(job_id)
        return self.with_resolution(job) if job else None

    def list_jobs(self) -> list[DownloadJob]:
        return [self.with_resolution(job) for job in self.repository.list_jobs()]

    def create_job(
        self,
        scan_id: str,
        episode_ids: list[str],
        quality: str,
        output_dir: str,
        parallel_limit: int,
    ) -> DownloadJob:
        scan = self.repository.get_scan(scan_id)
        if not scan or not scan.catalog:
            raise ValueError("Каталог не знайдено. Виконайте пошук знову.")
        catalog = scan.catalog
        return self.create_job_from_catalog(scan_id, catalog, episode_ids, quality, output_dir, parallel_limit)

    def create_job_from_catalog(
        self,
        scan_id: str,
        catalog: Catalog,
        episode_ids: list[str],
        quality: str,
        output_dir: str,
        parallel_limit: int,
    ) -> DownloadJob:
        selected = [episode for episode in catalog.episodes if episode.id in set(episode_ids)]
        if not selected or len(selected) != len(set(episode_ids)):
            raise ValueError("Виберіть серії зі знайденого списку.")

        if quality in ("max", "MAX", "Максимальна"):
            if any(not episode.variants for episode in selected):
                raise ValueError("Для деяких вибраних серій немає доступних варіантів якості.")

            def best_variant(ep: Episode) -> Variant:
                return max(ep.variants, key=lambda v: (v.height, v.bandwidth))

            estimated = sum(best_variant(episode).estimated_bytes for episode in selected)
            dimensions = {(best_variant(episode).width, best_variant(episode).height) for episode in selected
                          if best_variant(episode).width and best_variant(episode).height}
            if len(dimensions) == 1:
                width, height = next(iter(dimensions))
                resolution_label = f"{width} × {height}"
            else:
                resolution_label = "Різна роздільність" if dimensions else "Максимальна"
        else:
            if any(not any(variant.label == quality for variant in episode.variants) for episode in selected):
                raise ValueError("Обрана якість доступна не для всіх вибраних серій.")
            estimated = sum(next(variant.estimated_bytes for variant in episode.variants if variant.label == quality) for episode in selected)
            dimensions = {(variant.width, variant.height) for episode in selected for variant in episode.variants
                          if variant.label == quality and variant.width and variant.height}
            if len(dimensions) == 1:
                width, height = next(iter(dimensions))
                resolution_label = f"{width} × {height}"
            else:
                resolution_label = "Різна роздільність" if dimensions else quality

        if parallel_limit < 1 or parallel_limit > min(35, len(selected)):
            raise ValueError("Недопустима кількість паралельних завантажень.")
        root = Path(output_dir).expanduser()
        if not root.is_dir():
            raise ValueError("Вибрана папка не існує або недоступна.")
        if not self.downloader.has_required_tools():
            raise ValueError("Не знайдено FFmpeg або ffprobe. Встановіть FFmpeg і запустіть застосунок знову.")
        if self.system.get_free_disk_space(root) < int(estimated * 1.15):
            raise ValueError("У вибраній папці недостатньо вільного місця.")

        progress = [
            EpisodeProgress(episode_id=episode.id, number=episode.number, season=episode.season, voice=episode.voice)
            for episode in selected
        ]
        job = DownloadJob(
            id=uuid4().hex,
            catalog_id=scan_id,
            title=catalog.title,
            quality=quality,
            resolution=resolution_label,
            output_dir=str(root),
            parallel_limit=parallel_limit,
            episodes=progress,
            estimated_bytes=estimated,
        )
        self.repository.save_job(job)
        try:
            self.tasks[job.id] = asyncio.create_task(self._run(job.id))
        except RuntimeError:
            # If called outside a running event loop (e.g. sync unit test without loop)
            pass
        return job

    async def cancel_job(self, job_id: str) -> DownloadJob:
        job = self.repository.get_job(job_id)
        if not job:
            raise ValueError("Завдання не знайдено.")
        self.cancelled.add(job_id)
        self.downloader.cancel_download(job_id)
        if job_id not in self.tasks:
            job.status = "cancelled"
            self.repository.save_job(job)
        return job

    async def retry_job(self, job_id: str) -> DownloadJob:
        job = self.repository.get_job(job_id)
        if not job:
            raise ValueError("Завдання не знайдено.")
        if job_id in self.tasks and not self.tasks[job_id].done():
            raise ValueError("Завдання ще виконується.")
        if not any(episode.status in ("failed", "cancelled") for episode in job.episodes):
            raise ValueError("У завданні немає серій для повторного завантаження.")
        scan = self.repository.get_scan(job.catalog_id)
        if not scan or not scan.catalog:
            raise ValueError("Каталог не знайдено. Виконайте пошук ще раз.")

        if not job.resolution:
            selected = {episode.episode_id for episode in job.episodes}
            if job.quality in ("max", "MAX", "Максимальна"):
                dimensions = {
                    (max(ep.variants, key=lambda v: (v.height, v.bandwidth)).width,
                     max(ep.variants, key=lambda v: (v.height, v.bandwidth)).height)
                    for ep in scan.catalog.episodes if ep.id in selected and ep.variants
                }
                dimensions = {(w, h) for (w, h) in dimensions if w and h}
            else:
                dimensions = {(variant.width, variant.height) for episode in scan.catalog.episodes if episode.id in selected
                              for variant in episode.variants if variant.label == job.quality and variant.width and variant.height}
            if len(dimensions) == 1:
                width, height = next(iter(dimensions))
                job.resolution = f"{width} × {height}"
            elif dimensions:
                job.resolution = "Різна роздільність"

        for episode in job.episodes:
            if episode.status in ("failed", "cancelled"):
                episode.status = "queued"
                episode.error = None
                episode.percent = 0

        self.cancelled.discard(job_id)
        job.status = "queued"
        self.repository.save_job(job)
        try:
            self.tasks[job.id] = asyncio.create_task(self._run(job.id))
        except RuntimeError:
            # If called outside a running event loop (e.g. sync unit test without loop)
            pass
        return job

    async def delete_file(self, job_id: str, episode_id: str) -> DownloadJob:
        job = self.repository.get_job(job_id)
        if not job:
            raise ValueError("Завдання не знайдено.")
        if job_id in self.tasks and not self.tasks[job_id].done():
            raise ValueError("Дочекайтеся завершення завдання перед видаленням файлу.")
        episode = next((item for item in job.episodes if item.episode_id == episode_id), None)
        if not episode or episode.status != "complete" or not episode.output_file:
            raise ValueError("Готовий файл цієї серії не знайдено в завданні.")

        root = Path(job.output_dir).resolve()
        target = Path(episode.output_file).resolve()
        if not target.is_relative_to(root) or target.suffix.lower() != ".mp4":
            raise ValueError("Шлях файлу виходить за межі папки завантаження.")
        if not target.is_file():
            raise ValueError("Файл уже відсутній на диску.")

        try:
            target.unlink()
        except OSError as error:
            raise ValueError(f"Не вдалося видалити файл: {error}") from error

        playlist = target.parent / "Сезон.m3u8"
        try:
            if playlist.resolve().is_relative_to(root) and playlist.is_file():
                lines = playlist.read_text(encoding="utf-8").splitlines()
                remaining = [line for line in lines if line != target.name]
                if remaining != lines:
                    if any(line and not line.startswith("#") for line in remaining):
                        playlist.write_text("\n".join(remaining) + "\n", encoding="utf-8")
                    else:
                        playlist.unlink()
        except OSError as error:
            episode.error = f"Файл видалено, але плейлист не вдалося оновити: {error}"

        episode.status = "deleted"
        episode.percent = 0
        episode.bytes_written = 0
        episode.output_file = None
        statuses = {item.status for item in job.episodes}
        if statuses == {"deleted"}:
            job.status = "deleted"
        elif statuses <= {"complete", "deleted"}:
            job.status = "mixed"

        await self._publish(job)
        return job

    async def delete_job(self, job_id: str, delete_files: bool = False) -> None:
        job = self.repository.get_job(job_id)
        if not job:
            raise ValueError("Завдання не знайдено.")

        self.cancelled.add(job_id)
        self.downloader.cancel_download(job_id)
        if job_id in self.tasks:
            task = self.tasks.pop(job_id)
            if not task.done():
                task.cancel()

        if delete_files:
            root = Path(job.output_dir).resolve()
            parent_dirs: set[Path] = set()
            for episode in job.episodes:
                if episode.output_file:
                    target = Path(episode.output_file).resolve()
                    if target.is_relative_to(root) and target.suffix.lower() == ".mp4" and target.is_file():
                        parent_dirs.add(target.parent)
                        try:
                            target.unlink()
                        except OSError:
                            pass
            for parent in parent_dirs:
                try:
                    playlist = parent / "Сезон.m3u8"
                    if playlist.resolve().is_relative_to(root) and playlist.is_file():
                        playlist.unlink()
                    if parent.resolve().is_relative_to(root) and parent != root and not any(parent.iterdir()):
                        parent.rmdir()
                        if parent.parent.resolve().is_relative_to(root) and parent.parent != root and not any(parent.parent.iterdir()):
                            parent.parent.rmdir()
                except OSError:
                    pass

        self.repository.delete_job(job_id)
        await self.publisher.publish({"type": "job_deleted", "job_id": job_id})

    async def _publish(self, job: DownloadJob) -> None:
        self.repository.save_job(job)
        await self.publisher.publish({"type": "job", "job": job.model_dump(mode="json")})

    async def _run(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        scan = self.repository.get_scan(job.catalog_id) if job else None
        if not job or not scan or not scan.catalog:
            return

        catalog = scan.catalog
        episode_map = {episode.id: episode for episode in catalog.episodes}
        job.status = "downloading"
        await self._publish(job)
        semaphore = asyncio.Semaphore(job.parallel_limit)

        async def run_one(progress: EpisodeProgress) -> None:
            async with semaphore:
                if job.id in self.cancelled:
                    progress.status = "cancelled"
                    return
                episode = episode_map[progress.episode_id]
                await self._download_one(job, progress, episode, catalog)

        await asyncio.gather(*(run_one(progress) for progress in job.episodes if progress.status == "queued"))
        statuses = {progress.status for progress in job.episodes}
        if job.id in self.cancelled:
            job.status = "cancelled"
        elif statuses == {"complete"}:
            job.status = "complete"
        elif statuses == {"deleted"}:
            job.status = "deleted"
        elif statuses <= {"complete", "deleted"}:
            job.status = "mixed"
        elif "complete" in statuses:
            job.status = "partial"
        else:
            job.status = "failed"

        if job.status == "complete" and len(job.episodes) > 1:
            self._write_playlist(job)

        await self._publish(job)
        self.tasks.pop(job.id, None)

    def _write_playlist(self, job: DownloadJob) -> None:
        by_season: dict[Path, list[EpisodeProgress]] = {}
        for episode in job.episodes:
            if episode.output_file:
                by_season.setdefault(Path(episode.output_file).parent, []).append(episode)
        for folder, episodes in by_season.items():
            if len(episodes) < 2:
                continue
            lines = ["#EXTM3U"]
            lines.extend(Path(episode.output_file).name for episode in sorted(episodes, key=lambda item: item.number) if episode.output_file)
            (folder / "Сезон.m3u8").write_text("\n".join(lines) + "\n", encoding="utf-8")

    async def _download_one(self, job: DownloadJob, progress: EpisodeProgress, episode: Episode, catalog: Catalog) -> None:
        season = f"Сезон {episode.season}" if episode.season else "Фільм"
        destination = Path(job.output_dir) / safe_name(catalog.title) / season
        destination.mkdir(parents=True, exist_ok=True)
        label = f"S{episode.season:02d}E{episode.number:02d}" if episode.season else "Фільм"

        if job.quality in ("max", "MAX", "Максимальна"):
            chosen_variant = max(episode.variants, key=lambda v: (v.height, v.bandwidth)) if episode.variants else None
            actual_quality = chosen_variant.label if chosen_variant else "max"
            estimated_duration = chosen_variant.duration_seconds if chosen_variant else 0
        else:
            actual_quality = job.quality
            estimated_duration = next(variant.duration_seconds for variant in episode.variants if variant.label == job.quality)

        filename = safe_name(f"{catalog.title} {label} ({episode.voice}, {actual_quality})") + ".mp4"
        final = destination / filename
        partial = destination / (filename.removesuffix(".mp4") + ".part.mp4")

        if await self.downloader.verify_video(final, estimated_duration):
            progress.status = "complete"
            progress.percent = 100
            progress.bytes_written = final.stat().st_size
            progress.output_file = str(final)
            await self._publish(job)
            return

        progress.status = "downloading"
        await self._publish(job)
        error = "Невідома помилка"

        for attempt in range(1, 4):
            if job.id in self.cancelled:
                break
            if partial.exists():
                partial.unlink()

            try:
                variants = await self.source.resolve(episode, catalog.source_url)
                if job.quality in ("max", "MAX", "Максимальна"):
                    variant = max(variants, key=lambda v: (v.height, v.bandwidth)) if variants else None
                else:
                    variant = next((item for item in variants if item.label == job.quality), None)
                if not variant:
                    raise RuntimeError("Обрана якість більше не доступна.")

                async def on_progress(percent: float, bytes_written: int, speed: str) -> None:
                    progress.percent = percent
                    progress.bytes_written = bytes_written
                    progress.speed = speed
                    await self._publish(job)

                await self.downloader.download_stream(
                    job.id,
                    progress.episode_id,
                    variant.playlist_url,
                    variant.referer,
                    partial,
                    variant.duration_seconds,
                    on_progress=on_progress,
                )

                if job.id in self.cancelled:
                    break
                if not await self.downloader.verify_video(partial, variant.duration_seconds):
                    raise RuntimeError("Отриманий файл неповний або не містить відео й аудіо.")

                partial.replace(final)
                progress.status = "complete"
                progress.percent = 100
                progress.bytes_written = final.stat().st_size
                progress.output_file = str(final)
                progress.error = None
                await self._publish(job)
                return
            except Exception as exception:
                error = str(exception)
                progress.error = f"Спроба {attempt}/3: {error}"
                await self._publish(job)
                if attempt < 3:
                    await asyncio.sleep(attempt * 2)

        if partial.exists():
            partial.unlink()
        progress.status = "cancelled" if job.id in self.cancelled else "failed"
        progress.error = None if progress.status == "cancelled" else error
        await self._publish(job)
