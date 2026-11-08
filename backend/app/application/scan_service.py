from __future__ import annotations

import asyncio
from uuid import uuid4

from app.domain.models import Catalog, Episode, ScanState
from app.domain.security import normalize_source_url
from app.ports.inbound.scan import ScanUseCase
from app.ports.outbound.publisher import EventPublisherPort
from app.ports.outbound.repository import JobRepository
from app.ports.outbound.source import MediaSourcePort


class ScanService(ScanUseCase):
    def __init__(
        self,
        source: MediaSourcePort,
        repository: JobRepository,
        publisher: EventPublisherPort,
    ) -> None:
        self.source = source
        self.repository = repository
        self.publisher = publisher

    def get_scan(self, scan_id: str) -> ScanState | None:
        return self.repository.get_scan(scan_id)

    async def start_scan(self, raw_url: str) -> ScanState:
        item = ScanState(id=uuid4().hex)
        self.repository.save_scan(item)

        async def run() -> None:
            try:
                source_meta = normalize_source_url(raw_url)

                async def on_progress(done: int, total: int) -> None:
                    item.done = done
                    item.total = total
                    item.message = f"Перевіряємо якість: {done}/{total}"
                    self.repository.save_scan(item)
                    await self.publisher.publish({"type": "scan", "scan": item.model_dump(mode="json")})

                title, season, episodes = await self.source.discover(source_meta.canonical_url)
                if not episodes:
                    raise RuntimeError("Серії на сторінці не знайдено.")

                semaphore = asyncio.Semaphore(6)
                completed = 0

                async def inspect(episode: Episode) -> None:
                    nonlocal completed
                    async with semaphore:
                        try:
                            episode.variants = await self.source.resolve(episode, source_meta.canonical_url)
                        except Exception:
                            episode.variants = []
                        completed += 1
                        await on_progress(completed, len(episodes))

                await asyncio.gather(*(inspect(ep) for ep in episodes))
                if not any(ep.variants for ep in episodes):
                    raise RuntimeError("Жоден відеопотік не відкрився. Спробуйте пізніше або перевірте сторінку сайту.")

                catalog = Catalog(
                    id=uuid4().hex,
                    source_url=source_meta.canonical_url,
                    site=source_meta.site,  # type: ignore[arg-type]
                    title=title,
                    season=season,
                    episodes=episodes,
                )
                item.catalog = catalog
                item.status = "complete"
                item.message = f"Знайдено {len(catalog.episodes)} серій"
            except Exception as error:
                item.status = "failed"
                item.error = str(error)
                item.message = "Пошук не вдався"

            self.repository.save_scan(item)
            await self.publisher.publish({"type": "scan", "scan": item.model_dump(mode="json")})

        asyncio.create_task(run())
        return item
