from __future__ import annotations

import secrets
import shutil
from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException

from app.adapters.inbound.web.dto import DeleteFileRequest, DownloadRequest, FolderRequest, ScanRequest
from app.ports.inbound.folder import FolderUseCase
from app.ports.inbound.jobs import JobManagementUseCase
from app.ports.inbound.scan import ScanUseCase


def create_api_router(
    scan_use_case: ScanUseCase,
    job_use_case: JobManagementUseCase,
    folder_use_case: FolderUseCase,
    token_getter: Callable[[], str],
) -> APIRouter:
    router = APIRouter()

    def require_token(x_app_token: str | None = Header(default=None)) -> None:
        if not secrets.compare_digest(x_app_token or "", token_getter()):
            raise HTTPException(401, "Відкрийте застосунок через його локальну адресу запуску.")

    @router.get("/api/health")
    async def health():
        return {"status": "ok", "ffmpeg": bool(shutil.which("ffmpeg"))}

    @router.post("/api/scans", dependencies=[Depends(require_token)])
    async def create_scan(request: ScanRequest):
        return await scan_use_case.start_scan(request.url)

    @router.get("/api/scans/{scan_id}", dependencies=[Depends(require_token)])
    async def get_scan(scan_id: str):
        item = scan_use_case.get_scan(scan_id)
        if not item:
            raise HTTPException(404, "Пошук не знайдено.")
        return item

    @router.get("/api/jobs", dependencies=[Depends(require_token)])
    async def list_jobs():
        return job_use_case.list_jobs()

    @router.get("/api/jobs/{job_id}", dependencies=[Depends(require_token)])
    async def get_job(job_id: str):
        job = job_use_case.get_job(job_id)
        if not job:
            raise HTTPException(404, "Завдання не знайдено.")
        return job

    @router.post("/api/jobs", dependencies=[Depends(require_token)])
    async def create_job(request: DownloadRequest):
        try:
            return job_use_case.create_job(
                scan_id=request.catalog_id,
                episode_ids=request.episode_ids,
                quality=request.quality,
                output_dir=request.output_dir,
                parallel_limit=request.parallel_limit,
            )
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.post("/api/jobs/{job_id}/cancel", dependencies=[Depends(require_token)])
    async def cancel_job(job_id: str):
        try:
            return await job_use_case.cancel_job(job_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.post("/api/jobs/{job_id}/retry", dependencies=[Depends(require_token)])
    async def retry_job(job_id: str):
        try:
            return await job_use_case.retry_job(job_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.post("/api/jobs/{job_id}/delete-file", dependencies=[Depends(require_token)])
    async def delete_file(job_id: str, request: DeleteFileRequest):
        try:
            return await job_use_case.delete_file(job_id, request.episode_id)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.delete("/api/jobs/{job_id}", dependencies=[Depends(require_token)])
    async def delete_job(job_id: str, delete_files: bool = False):
        try:
            await job_use_case.delete_job(job_id, delete_files=delete_files)
            return {"status": "ok", "job_id": job_id}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.post("/api/jobs/{job_id}/delete", dependencies=[Depends(require_token)])
    async def delete_job_post(job_id: str, delete_files: bool = False):
        try:
            await job_use_case.delete_job(job_id, delete_files=delete_files)
            return {"status": "ok", "job_id": job_id}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/api/folder", dependencies=[Depends(require_token)])
    async def get_folder():
        return {"path": folder_use_case.get_downloads_folder()}

    @router.put("/api/folder", dependencies=[Depends(require_token)])
    async def save_folder(request: FolderRequest):
        return {"path": folder_use_case.set_downloads_folder(request.path)}

    @router.post("/api/folder/select", dependencies=[Depends(require_token)])
    async def choose_folder(request: FolderRequest):
        return {"path": await folder_use_case.open_folder_picker(request.path)}

    return router
