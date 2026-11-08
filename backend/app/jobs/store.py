from __future__ import annotations

from app.adapters.outbound.persistence.sqlite_repository import SqliteRepository

Store = SqliteRepository

__all__ = ["SqliteRepository", "Store"]
