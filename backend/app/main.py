from __future__ import annotations

import asyncio
import base64
import os
import secrets
import shutil
import subprocess
import winreg
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.jobs.manager import JobManager
from app.jobs.store import Store
from app.models import DownloadJob, ScanState
from app.sources.registry import scan as scan_source


class ScanRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    catalog_id: str
    episode_ids: list[str]
    quality: str
    output_dir: str
    parallel_limit: int = 1


class FolderRequest(BaseModel):
    path: str = ""


class DeleteFileRequest(BaseModel):
    episode_id: str


def default_downloads_folder() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            raw = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")[0]
            return os.path.expandvars(raw)
    except OSError:
        return str(Path.home() / "Downloads")


def create_app(data_dir: Path | None = None, token: str | None = None) -> FastAPI:
    app = FastAPI(title="Кадр — завантаження серіалів")
    app.state.token = token or secrets.token_urlsafe(32)
    default_data = Path(os.environ.get("KADR_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "KadrDownloader"))
    app.state.store = Store((data_dir or default_data) / "state.sqlite3")
    app.state.clients: set[WebSocket] = set()

    async def notify(payload: dict) -> None:
        for client in list(app.state.clients):
            try:
                await client.send_json(payload)
            except Exception:
                app.state.clients.discard(client)

    app.state.manager = JobManager(app.state.store, notify)

    def with_resolution(job: DownloadJob) -> DownloadJob:
        if job.resolution:
            return job
        scan = app.state.store.get_scan(job.catalog_id)
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

    def require_token(x_app_token: str | None = Header(default=None)) -> None:
        if not secrets.compare_digest(x_app_token or "", app.state.token):
            raise HTTPException(401, "Відкрийте застосунок через його локальну адресу запуску.")

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "ffmpeg": bool(shutil.which("ffmpeg"))}

    @app.post("/api/scans", dependencies=[Depends(require_token)])
    async def create_scan(request: ScanRequest):
        item = ScanState(id=uuid4().hex)
        app.state.store.save_scan(item)

        async def run() -> None:
            try:
                async def progress(done: int, total: int) -> None:
                    item.done, item.total = done, total
                    item.message = f"Перевіряємо якість: {done}/{total}"
                    app.state.store.save_scan(item)
                    await notify({"type": "scan", "scan": item.model_dump(mode="json")})

                catalog = await scan_source(request.url, progress)
                item.catalog = catalog
                item.status = "complete"
                item.message = f"Знайдено {len(catalog.episodes)} серій"
            except Exception as error:
                item.status = "failed"
                item.error = str(error)
                item.message = "Пошук не вдався"
            app.state.store.save_scan(item)
            await notify({"type": "scan", "scan": item.model_dump(mode="json")})

        asyncio.create_task(run())
        return item

    @app.get("/api/scans/{scan_id}", dependencies=[Depends(require_token)])
    async def get_scan(scan_id: str):
        item = app.state.store.get_scan(scan_id)
        if not item:
            raise HTTPException(404, "Пошук не знайдено.")
        return item

    @app.get("/api/jobs", dependencies=[Depends(require_token)])
    async def list_jobs():
        return [with_resolution(job) for job in app.state.store.list_jobs()]

    @app.get("/api/jobs/{job_id}", dependencies=[Depends(require_token)])
    async def get_job(job_id: str):
        job = app.state.store.get_job(job_id)
        if not job:
            raise HTTPException(404, "Завдання не знайдено.")
        return with_resolution(job)

    @app.post("/api/jobs", dependencies=[Depends(require_token)])
    async def create_job(request: DownloadRequest):
        item = app.state.store.get_scan(request.catalog_id)
        if not item or not item.catalog:
            raise HTTPException(404, "Каталог не знайдено. Виконайте пошук знову.")
        try:
            return app.state.manager.create(item.id, item.catalog, request.episode_ids, request.quality,
                                            request.output_dir, request.parallel_limit)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/api/jobs/{job_id}/cancel", dependencies=[Depends(require_token)])
    async def cancel_job(job_id: str):
        try:
            return await app.state.manager.cancel(job_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/api/jobs/{job_id}/retry", dependencies=[Depends(require_token)])
    async def retry_job(job_id: str):
        try:
            return await app.state.manager.retry(job_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/api/jobs/{job_id}/delete-file", dependencies=[Depends(require_token)])
    async def delete_file(job_id: str, request: DeleteFileRequest):
        try:
            return await app.state.manager.delete_file(job_id, request.episode_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.delete("/api/jobs/{job_id}", dependencies=[Depends(require_token)])
    async def delete_job(job_id: str, delete_files: bool = False):
        try:
            await app.state.manager.delete(job_id, delete_files=delete_files)
            return {"status": "ok", "job_id": job_id}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/api/jobs/{job_id}/delete", dependencies=[Depends(require_token)])
    async def delete_job_post(job_id: str, delete_files: bool = False):
        try:
            await app.state.manager.delete(job_id, delete_files=delete_files)
            return {"status": "ok", "job_id": job_id}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/api/folder", dependencies=[Depends(require_token)])
    async def get_folder():
        return {"path": app.state.store.get_setting("output_dir") or default_downloads_folder()}

    @app.put("/api/folder", dependencies=[Depends(require_token)])
    async def save_folder(request: FolderRequest):
        app.state.store.set_setting("output_dir", request.path.strip())
        return {"path": request.path.strip()}

    @app.post("/api/folder/select", dependencies=[Depends(require_token)])
    async def choose_folder(request: FolderRequest):
        encoded_path = base64.b64encode(request.path.encode("utf-8")).decode("ascii")
        command = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; "
                   f"$selected=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded_path}')); "
                   "$d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Оберіть папку для завантаження'; "
                   "if($selected -and [IO.Directory]::Exists($selected)) { $d.SelectedPath=$selected }; "
                   "if($d.ShowDialog() -eq 'OK') { [Console]::Write($d.SelectedPath) }")
        process = await asyncio.to_thread(subprocess.run,
                                          ["powershell", "-NoProfile", "-STA", "-Command", command],
                                          capture_output=True, text=True, encoding="utf-8", timeout=300)
        path = process.stdout.strip() if process.returncode == 0 else ""
        if path:
            app.state.store.set_setting("output_dir", path)
        return {"path": path}

    @app.websocket("/api/events")
    async def events(websocket: WebSocket):
        if not secrets.compare_digest(websocket.query_params.get("token", ""), app.state.token):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        app.state.clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            app.state.clients.discard(websocket)

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        async def frontend(path: str):
            candidate = (dist / path).resolve()
            if path and candidate.is_relative_to(dist.resolve()) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
