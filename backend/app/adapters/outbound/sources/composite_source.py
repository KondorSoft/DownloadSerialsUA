from __future__ import annotations

from app.domain.models import Episode, Variant
from app.domain.security import normalize_source_url
from app.ports.outbound.source import MediaSourcePort
from app.adapters.outbound.sources import uaflix, uakino
from app.adapters.outbound.sources.http import SourceHttp


class CompositeMediaSourceAdapter(MediaSourcePort):
    def __init__(self, http: SourceHttp | None = None) -> None:
        self._http = http

    def _get_http(self) -> SourceHttp:
        return self._http or SourceHttp()

    def can_handle(self, url: str) -> bool:
        try:
            normalize_source_url(url)
            return True
        except ValueError:
            return False

    async def discover(self, url: str) -> tuple[str, int | None, list[Episode]]:
        source = normalize_source_url(url)
        http = self._get_http()
        should_close = self._http is None
        try:
            if source.site == "UAKINO":
                raw_title, items = await uakino.discover(source.canonical_url)
                title, season = uakino.title_and_season(raw_title)
                episodes = [uakino.episode_from_item(item, season) for item in items]
                return title, season, episodes
            else:
                return await uaflix.discover(http, source.canonical_url)
        finally:
            if should_close:
                await http.close()

    async def resolve(self, episode: Episode, page_url: str) -> list[Variant]:
        source = normalize_source_url(page_url)
        http = self._get_http()
        should_close = self._http is None
        try:
            if source.site == "UAKINO":
                return await uakino.resolve(http, episode.source_url, page_url)
            return await uaflix.resolve(http, episode.source_url)
        finally:
            if should_close:
                await http.close()
