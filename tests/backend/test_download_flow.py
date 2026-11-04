import asyncio
import functools
import shutil
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.jobs.manager import JobManager, valid_video
from app.jobs.store import Store
from app.main import create_app
from app.models import Catalog, Episode, ScanState, Variant


def test_api_requires_local_token(tmp_path):
    app = create_app(tmp_path, token="test-token")
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/jobs").status_code == 401
        assert client.get("/api/jobs", headers={"X-App-Token": "test-token"}).status_code == 200


def test_folder_setting_survives_restart(tmp_path):
    headers = {"X-App-Token": "test-token"}
    with TestClient(create_app(tmp_path, token="test-token")) as client:
        assert client.get("/api/folder", headers=headers).json()["path"]
        assert client.put("/api/folder", headers=headers, json={"path": str(tmp_path)}).status_code == 200
    with TestClient(create_app(tmp_path, token="test-token")) as client:
        assert client.get("/api/folder", headers=headers).json()["path"] == str(tmp_path)


def test_folder_picker_saves_selected_path(tmp_path, monkeypatch):
    def chosen_folder(command, **kwargs):
        assert "FolderBrowserDialog" in command[4]
        assert "Оберіть папку" in command[4]
        assert kwargs["encoding"] == "utf-8"
        return subprocess.CompletedProcess(command, 0, stdout=str(tmp_path), stderr="")

    monkeypatch.setattr("app.main.subprocess.run", chosen_folder)
    headers = {"X-App-Token": "test-token"}
    with TestClient(create_app(tmp_path, token="test-token")) as client:
        response = client.post("/api/folder/select", headers=headers, json={"path": str(tmp_path)})
        assert response.json()["path"] == str(tmp_path)
        assert client.get("/api/folder", headers=headers).json()["path"] == str(tmp_path)


def test_scan_catalog_survives_restart(tmp_path):
    store = Store(tmp_path / "state.sqlite3")
    variant = Variant(label="720p", width=1280, height=720, bandwidth=1_000_000,
                      duration_seconds=4, estimated_bytes=500_000,
                      playlist_url="https://ashdi.vip/hls/720/index.m3u8", referer="https://ashdi.vip/vod/1")
    catalog = Catalog(id="catalog", source_url="https://uakino.best/series.html", site="UAKINO", title="Тест",
                      season=2, episodes=[Episode(id="https://ashdi.vip/vod/1", number=1, season=2,
                                                  voice="Українська", source_url="https://ashdi.vip/vod/1", variants=[variant])])
    store.save_scan(ScanState(id="scan", status="complete", catalog=catalog))
    store.close()
    restored = Store(tmp_path / "state.sqlite3").get_scan("scan")
    assert restored.catalog.episodes[0].variants[0].label == "720p"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_parallel_job_writes_verified_videos(tmp_path, monkeypatch):
    playlist = tmp_path / "source.m3u8"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=25",
        "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100", "-t", "3", "-c:v", "libx264",
        "-c:a", "aac", "-hls_time", "1", "-hls_playlist_type", "vod", str(playlist),
    ], check=True)
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    variant = Variant(label="180p", width=320, height=180, bandwidth=500_000,
                      duration_seconds=3, estimated_bytes=200_000,
                      playlist_url=f"http://127.0.0.1:{server.server_port}/source.m3u8",
                      referer="https://ashdi.vip/vod/1")
    episodes = [Episode(id=f"https://ashdi.vip/vod/{number}", number=number, season=1, voice="Тест",
                        source_url=f"https://ashdi.vip/vod/{number}", variants=[variant]) for number in (1, 2)]
    catalog = Catalog(id="catalog", source_url="https://uakino.best/series.html", site="UAKINO",
                      title="Тестовий сезон", season=1, episodes=episodes)
    store = Store(tmp_path / "state.sqlite3")
    store.save_scan(ScanState(id="scan", status="complete", catalog=catalog))

    async def fake_resolve(http, site, episode, page_url):
        return [variant]

    monkeypatch.setattr("app.jobs.manager.resolve_episode", fake_resolve)

    async def run():
        manager = JobManager(store, lambda payload: asyncio.sleep(0))
        job = manager.create("scan", catalog, [episode.id for episode in episodes], "180p", str(tmp_path), 2)
        await asyncio.wait_for(manager.tasks[job.id], 30)
        finished = store.get_job(job.id)
        assert finished.status == "complete", [item.error for item in finished.episodes]
        assert len(finished.episodes) == 2
        for item in finished.episodes:
            assert item.status == "complete"
            assert await valid_video(Path(item.output_file), 3)
        playlist = Path(finished.episodes[0].output_file).parent / "Сезон.m3u8"
        assert playlist.read_text(encoding="utf-8").splitlines() == [
            "#EXTM3U", *[Path(item.output_file).name for item in finished.episodes]
        ]
        first_file = Path(finished.episodes[0].output_file)
        second_file = Path(finished.episodes[1].output_file)
        after_first = await manager.delete_file(job.id, episodes[0].id)
        assert after_first.status == "mixed"
        assert after_first.episodes[0].status == "deleted"
        assert not first_file.exists()
        assert playlist.read_text(encoding="utf-8").splitlines() == ["#EXTM3U", second_file.name]
        after_second = await manager.delete_file(job.id, episodes[1].id)
        assert after_second.status == "deleted"
        assert not second_file.exists()
        assert not playlist.exists()

    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()


def test_delete_file_rejects_path_outside_job_folder(tmp_path):
    from app.models import DownloadJob, EpisodeProgress

    folder = tmp_path / "downloads"
    folder.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    store = Store(tmp_path / "state.sqlite3")
    job = DownloadJob(id="job", catalog_id="scan", title="Тест", quality="800p",
                      output_dir=str(folder), parallel_limit=1, estimated_bytes=10,
                      status="complete", episodes=[EpisodeProgress(episode_id="episode", number=1, voice="Тест",
                      status="complete", output_file=str(outside))])
    store.save_job(job)

    async def run():
        manager = JobManager(store, lambda payload: asyncio.sleep(0))
        with pytest.raises(ValueError, match="за межі"):
            await manager.delete_file("job", "episode")

    asyncio.run(run())
    assert outside.exists()


def test_delete_file_api_updates_job_and_keeps_unrelated_file(tmp_path):
    from app.models import DownloadJob, EpisodeProgress

    video = tmp_path / "film.mp4"
    video.write_bytes(b"video")
    unrelated = tmp_path / "other.mp4"
    unrelated.write_bytes(b"keep")
    app = create_app(tmp_path / "data", token="test-token")
    app.state.store.save_job(DownloadJob(id="job", catalog_id="scan", title="Фільм", quality="800p",
        output_dir=str(tmp_path), parallel_limit=1, estimated_bytes=10, status="complete",
        episodes=[EpisodeProgress(episode_id="film", number=1, voice="Українська", status="complete",
                                  percent=100, output_file=str(video))]))
    with TestClient(app) as client:
        url = "/api/jobs/job/delete-file"
        assert client.post(url, json={"episode_id": "film"}).status_code == 401
        response = client.post(url, headers={"X-App-Token": "test-token"}, json={"episode_id": "film"})
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        assert response.json()["episodes"][0]["status"] == "deleted"
    assert not video.exists()
    assert unrelated.exists()
