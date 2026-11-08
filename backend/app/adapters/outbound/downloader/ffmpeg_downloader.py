from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path

from app.ports.outbound.downloader import ProgressReporter, VideoDownloaderPort


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


class FFmpegDownloaderAdapter(VideoDownloaderPort):
    def __init__(self) -> None:
        self.processes: dict[tuple[str, str], asyncio.subprocess.Process] = {}

    def has_required_tools(self) -> bool:
        return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

    async def verify_video(self, path: Path, expected_duration: float) -> bool:
        return await valid_video(path, expected_duration)

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
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("Не знайдено FFmpeg. Встановіть FFmpeg і запустіть застосунок знову.")

        process = await asyncio.create_subprocess_exec(
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-stats_period",
            "0.5",
            "-progress",
            "pipe:1",
            "-headers",
            f"Referer: {referer}\r\nUser-Agent: Mozilla/5.0\r\n",
            "-i",
            playlist_url,
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-sn",
            "-c",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            str(output_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.processes[(job_id, episode_id)] = process
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
                    percent = round(min(99.9, seconds / duration * 100), 1) if duration else 0
                    bytes_written = int(values.get("total_size", "0") or 0)
                    speed = values.get("speed", "")

                    if on_progress:
                        await on_progress(percent, bytes_written, speed)

                    last_update = time.monotonic()
                    values.clear()

            await process.wait()
            stderr = (await stderr_task).decode("utf-8", errors="replace")
            if process.returncode:
                raise RuntimeError(stderr[-500:] or f"FFmpeg завершився з кодом {process.returncode}.")
        finally:
            self.processes.pop((job_id, episode_id), None)

    def cancel_download(self, job_id: str, episode_id: str | None = None) -> None:
        for (current_job, current_ep), process in list(self.processes.items()):
            if current_job == job_id and (episode_id is None or current_ep == episode_id):
                if process.returncode is None:
                    try:
                        process.terminate()
                    except Exception:
                        pass
