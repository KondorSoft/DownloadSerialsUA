from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import uuid4

from app.models import Catalog, Episode
from app.security import normalize_source_url
from app.sources import uaflix, uakino
from app.sources.http import SourceHttp


ProgressCallback = Callable[[int, int], Awaitable[None]]


async def scan(raw_url: str, progress: ProgressCallback | None = None) -> Catalog:
    source = normalize_source_url(raw_url)
    http = SourceHttp()
    try:
        if source.site == "UAKINO":
            raw_title, items = await uakino.discover(source.canonical_url)
            title, season = uakino.title_and_season(raw_title)
            episodes = [uakino.episode_from_item(item, season) for item in items]
        else:
            title, season, episodes = await uaflix.discover(http, source.canonical_url)
        if not episodes:
            raise RuntimeError("Серії на сторінці не знайдено.")
        semaphore = asyncio.Semaphore(6)
        completed = 0

        async def inspect(episode: Episode) -> None:
            nonlocal completed
            async with semaphore:
                try:
                    episode.variants = await resolve_episode(http, source.site, episode, source.canonical_url)
                except Exception:
                    episode.variants = []
                completed += 1
                if progress:
                    await progress(completed, len(episodes))

        await asyncio.gather(*(inspect(episode) for episode in episodes))
        if not any(episode.variants for episode in episodes):
            raise RuntimeError("Жоден відеопотік не відкрився. Спробуйте пізніше або перевірте сторінку сайту.")
        return Catalog(id=uuid4().hex, source_url=source.canonical_url, site=source.site,
                       title=title, season=season, episodes=episodes)
    finally:
        await http.close()


async def resolve_episode(http: SourceHttp, site: str, episode: Episode, page_url: str):
    if site == "UAKINO":
        return await uakino.resolve(http, episode.source_url, page_url)
    return await uaflix.resolve(http, episode.source_url)
