from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from pathlib import Path
from uuid import uuid4

from app.models import Catalog, DownloadJob, Episode, EpisodeProgress, Variant
from app.jobs.store import Store
from app.sources.http import SourceHttp
from app.sources.registry import resolve_episode


INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(raw: str) -> str:
    result = INVALID_NAME.sub("_", raw).strip(" .")
    return result[:110] or "Відео"


async def valid_video(path: Path, expected_duration: float) -> bool:
    if not path.exists() or path.stat().st_size < 1024:
        return False
    probe = shutil.which("ffprobe")
    if not probe:
        raise RuntimeError("Не знайдено ffprobe. Встановіть FFmpeg і запустіть застосунок знову.")
    process = await asyncio.create_subprocess_exec(
        probe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    if process.returncode:
        return False
    try:
        data = json.loads(stdout)
        duration = float(data["format"]["duration"])
        types = {stream["codec_type"] for stream in data["streams"]}
    except (ValueError, KeyError, TypeError):
        return False
    return duration >= expected_duration * 0.95 and {"audio", "video"} <= types


class JobManager:
    def __init__(self, store: Store, notify) -> None:
        self.store = store
        self.notify = notify
        self.tasks: dict[str, asyncio.Task] = {}
        self.processes: dict[tuple[str, str], asyncio.subprocess.Process] = {}
        self.cancelled: set[str] = set()

    def create(self, scan_id: str, catalog: Catalog, episode_ids: list[str], quality: str, output_dir: str, parallel_limit: int) -> DownloadJob:
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
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise ValueError("Не знайдено FFmpeg або ffprobe. Встановіть FFmpeg і запустіть застосунок знову.")
        if shutil.disk_usage(root).free < int(estimated * 1.15):
            raise ValueError("У вибраній папці недостатньо вільного місця.")
        progress = [EpisodeProgress(episode_id=episode.id, number=episode.number, season=episode.season, voice=episode.voice)
                    for episode in selected]
        job = DownloadJob(id=uuid4().hex, catalog_id=scan_id, title=catalog.title, quality=quality, resolution=resolution_label,
                          output_dir=str(root), parallel_limit=parallel_limit, episodes=progress, estimated_bytes=estimated)
        self.store.save_job(job)
        self.tasks[job.id] = asyncio.create_task(self._run(job.id))
        return job

    async def cancel(self, job_id: str) -> DownloadJob:
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError("Завдання не знайдено.")
        self.cancelled.add(job_id)
        for (current_id, _), process in list(self.processes.items()):
            if current_id == job_id and process.returncode is None:
                process.terminate()
        if job_id not in self.tasks:
            job.status = "cancelled"
            self.store.save_job(job)
        return job

    async def retry(self, job_id: str) -> DownloadJob:
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError("Завдання не знайдено.")
        if job_id in self.tasks and not self.tasks[job_id].done():
            raise ValueError("Завдання ще виконується.")
        if not any(episode.status in ("failed", "cancelled") for episode in job.episodes):
            raise ValueError("У завданні немає серій для повторного завантаження.")
        scan = self.store.get_scan(job.catalog_id)
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
        self.store.save_job(job)
        self.tasks[job.id] = asyncio.create_task(self._run(job.id))
        return job

    async def delete_file(self, job_id: str, episode_id: str) -> DownloadJob:
        job = self.store.get_job(job_id)
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

    async def delete(self, job_id: str, delete_files: bool = False) -> None:
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError("Завдання не знайдено.")
        self.cancelled.add(job_id)
        for (current_id, _), process in list(self.processes.items()):
            if current_id == job_id and process.returncode is None:
                try:
                    process.terminate()
                except Exception:
                    pass
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
        self.store.delete_job(job_id)
        await self.notify({"type": "job_deleted", "job_id": job_id})

    async def _publish(self, job: DownloadJob) -> None:
        self.store.save_job(job)
        await self.notify({"type": "job", "job": job.model_dump(mode="json")})

    async def _run(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        scan = self.store.get_scan(job.catalog_id)
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

        if await valid_video(final, estimated_duration):
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
            http = SourceHttp()
            try:
                variants = await resolve_episode(http, catalog.site, episode, catalog.source_url)
                if job.quality in ("max", "MAX", "Максимальна"):
                    variant = max(variants, key=lambda v: (v.height, v.bandwidth)) if variants else None
                else:
                    variant = next((item for item in variants if item.label == job.quality), None)
                if not variant:
                    raise RuntimeError("Обрана якість більше не доступна.")
                await self._ffmpeg(job, progress, variant.playlist_url, variant.referer, partial, variant.duration_seconds)
                if job.id in self.cancelled:
                    break
                if not await valid_video(partial, variant.duration_seconds):
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
            finally:
                await http.close()
        if partial.exists():
            partial.unlink()
        progress.status = "cancelled" if job.id in self.cancelled else "failed"
        progress.error = None if progress.status == "cancelled" else error
        await self._publish(job)

    async def _ffmpeg(self, job: DownloadJob, progress: EpisodeProgress, url: str, referer: str,
                      output: Path, duration: float) -> None:
        process = await asyncio.create_subprocess_exec(
            shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-stats_period", "0.5",
            "-progress", "pipe:1", "-headers", f"Referer: {referer}\r\nUser-Agent: Mozilla/5.0\r\n",
            "-i", url, "-map", "0:v:0", "-map", "0:a:0", "-sn", "-c", "copy", "-bsf:a", "aac_adtstoasc", str(output),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        self.processes[(job.id, progress.episode_id)] = process
        stderr_task = asyncio.create_task(process.stderr.read())
        values: dict[str, str] = {}
        last_update = 0.0
        try:
            while line := await process.stdout.readline():
                text = line.decode("utf-8", errors="replace").strip()
                if "=" not in text:
                    continue
                key, value = text.split("=", 1)
                values[key] = value
                if key == "progress" and time.monotonic() - last_update > 0.5:
                    seconds = float(values.get("out_time_us", values.get("out_time_ms", "0"))) / 1_000_000
                    progress.percent = round(min(99.9, seconds / duration * 100), 1) if duration else 0
                    progress.bytes_written = int(values.get("total_size", "0") or 0)
                    progress.speed = values.get("speed", "")
                    await self._publish(job)
                    last_update = time.monotonic()
                    values.clear()
            await process.wait()
            stderr = (await stderr_task).decode("utf-8", errors="replace")
            if process.returncode:
                raise RuntimeError(stderr[-500:] or f"FFmpeg завершився з кодом {process.returncode}.")
        finally:
            self.processes.pop((job.id, progress.episode_id), None)
