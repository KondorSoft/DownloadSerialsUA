from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.adapters.inbound.web import create_api_router, create_websocket_router
from app.adapters.outbound.downloader import FFmpegDownloaderAdapter
from app.adapters.outbound.persistence import SqliteRepository
from app.adapters.outbound.publisher import WebSocketEventPublisher
from app.adapters.outbound.sources import CompositeMediaSourceAdapter
from app.adapters.outbound.system import WindowsSystemAdapter
from app.application import FolderService, JobService, ScanService


def create_app(data_dir: Path | None = None, token: str | None = None) -> FastAPI:
    app = FastAPI(title="Кадр — завантаження серіалів")
    app_token = token or secrets.token_urlsafe(32)
    app.state.token = app_token

    # 1. Outbound / Driven Adapters
    default_data = Path(os.environ.get("KADR_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "KadrDownloader"))
    db_path = (data_dir or default_data) / "state.sqlite3"
    repository = SqliteRepository(db_path)
    system = WindowsSystemAdapter()
    downloader = FFmpegDownloaderAdapter()
    source = CompositeMediaSourceAdapter()
    publisher = WebSocketEventPublisher()

    # 2. Application Services / Use Cases
    folder_service = FolderService(settings=repository, system=system)
    scan_service = ScanService(source=source, repository=repository, publisher=publisher)
    job_service = JobService(
        repository=repository,
        downloader=downloader,
        source=source,
        system=system,
        publisher=publisher,
    )

    # Backward compatibility attributes on app.state
    app.state.store = repository
    app.state.manager = job_service
    app.state.clients = publisher.clients

    # 3. Inbound / Driving Adapters (Web / HTTP & WebSockets)
    api_router = create_api_router(
        scan_use_case=scan_service,
        job_use_case=job_service,
        folder_use_case=folder_service,
        token_getter=lambda: app.state.token,
    )
    ws_router = create_websocket_router(
        publisher=publisher,
        token_getter=lambda: app.state.token,
    )
    app.include_router(api_router)
    app.include_router(ws_router)

    # 4. Static frontend asset hosting
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
