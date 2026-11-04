from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.models import Episode
from app.sources.hls import inspect_master
from app.sources.http import SourceHttp


EPISODE_RE = re.compile(r"/season-(\d+)-episode-(\d+)/?$")
PLAYER_RE = re.compile(r'<iframe[^>]+src="(https://zetvideo\.net/vod/\d+)"', re.I)
FILE_RE = re.compile(r"\bfile\s*:\s*['\"]([^'\"]+)['\"]")


async def discover(http: SourceHttp, url: str) -> tuple[str, int | None, list[Episode]]:
    html = await http.get_text(url, kind="page")
    soup = BeautifulSoup(html, "html.parser")
    title_text = soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "Відео"
    page_match = EPISODE_RE.search(urlsplit(url).path)
    season_match = re.search(r"(?:/sezon-|season-)(\d+)", urlsplit(url).path)
    season = int(season_match.group(1)) if season_match else None
    title = re.sub(r"\s*\d+\s*сезон.*$", "", title_text, flags=re.I).strip()
    title = re.sub(r"\s*/\s*White Collar.*$", "", title, flags=re.I).strip() or title_text
    title = re.sub(r"\s+дивитись онлайн.*$", "", title, flags=re.I).strip() or title
    if urlsplit(url).path.startswith("/films/"):
        if soup.select_one('iframe[src^="https://zetvideo.net/vod/"]'):
            return title, None, [Episode(id=url, number=1, season=None, voice="Українська", source_url=url)]
        raise RuntimeError("На сторінці UAFLIX не знайдено плеєра фільму.")
    links: dict[tuple[int, int], str] = {}
    for anchor in soup.select("a[href]"):
        absolute = urljoin(url, anchor["href"])
        match = EPISODE_RE.search(urlsplit(absolute).path)
        if match:
            item_season, number = map(int, match.groups())
            if season is None or item_season == season:
                links[(item_season, number)] = absolute
    if page_match:
        item_season, number = map(int, page_match.groups())
        links[(item_season, number)] = url
    if not links:
        raise RuntimeError("На сторінці UAFLIX не знайдено посилань на серії.")
    episodes = [Episode(id=link, number=number, season=item_season, voice="UAFLIX", source_url=link)
                for (item_season, number), link in sorted(links.items())]
    return title, season, episodes


async def resolve(http: SourceHttp, page_url: str):
    html = await http.get_text(page_url, kind="page")
    match = PLAYER_RE.search(html)
    if not match:
        raise RuntimeError("На сторінці UAFLIX немає доступного плеєра.")
    player_url = match.group(1)
    player = await http.get_text(player_url, kind="media", referer="https://uafix.net/")
    stream_match = FILE_RE.search(player)
    if not stream_match:
        raise RuntimeError("Плеєр UAFLIX не повернув відеопотік.")
    return await inspect_master(http, stream_match.group(1), player_url)

