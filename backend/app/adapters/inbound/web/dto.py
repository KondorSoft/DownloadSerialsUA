from __future__ import annotations

from pydantic import BaseModel


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
