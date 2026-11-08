from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

from app.domain.models import DownloadJob, ScanState
from app.ports.outbound.repository import JobRepository, SettingsRepository


class SqliteRepository(JobRepository, SettingsRepository):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        with self.lock:
            self.db.execute("CREATE TABLE IF NOT EXISTS scans (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.db.commit()
        self.mark_interrupted()

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def _save(self, table: str, item_id: str, payload: str) -> None:
        with self.lock:
            self.db.execute(f"INSERT OR REPLACE INTO {table} (id, payload) VALUES (?, ?)", (item_id, payload))
            self.db.commit()

    def _get(self, table: str, item_id: str):
        with self.lock:
            row = self.db.execute(f"SELECT payload FROM {table} WHERE id=?", (item_id,)).fetchone()
        return row[0] if row else None

    def save_scan(self, scan: ScanState) -> None:
        self._save("scans", scan.id, scan.model_dump_json())

    def get_scan(self, scan_id: str) -> ScanState | None:
        raw = self._get("scans", scan_id)
        return ScanState.model_validate_json(raw) if raw else None

    def save_job(self, job: DownloadJob) -> None:
        self._save("jobs", job.id, job.model_dump_json())

    def get_job(self, job_id: str) -> DownloadJob | None:
        raw = self._get("jobs", job_id)
        return DownloadJob.model_validate_json(raw) if raw else None

    def delete_job(self, job_id: str) -> bool:
        with self.lock:
            cursor = self.db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            self.db.commit()
            return cursor.rowcount > 0

    def list_jobs(self, limit: int = 30) -> list[DownloadJob]:
        with self.lock:
            rows = self.db.execute("SELECT payload FROM jobs ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return [DownloadJob.model_validate_json(row[0]) for row in rows]

    def get_setting(self, key: str) -> str | None:
        with self.lock:
            row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            self.db.commit()

    def mark_interrupted(self) -> None:
        with self.lock:
            rows = self.db.execute("SELECT payload FROM jobs").fetchall()
            for (payload,) in rows:
                job = DownloadJob.model_validate_json(payload)
                if job.status in ("queued", "downloading"):
                    job.status = "interrupted"
                    for episode in job.episodes:
                        if episode.status in ("queued", "downloading"):
                            episode.status = "failed"
                            episode.error = "Роботу перервано. Натисніть «Повторити невдалі»."
                    self.db.execute("UPDATE jobs SET payload=? WHERE id=?", (job.model_dump_json(), job.id))
            self.db.commit()
