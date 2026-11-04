from __future__ import annotations

import asyncio
import os
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app.models import Episode
from app.sources.hls import inspect_master
from app.sources.http import SourceHttp
from app.security import validate_url


FILE_RE = re.compile(r"\bfile\s*:\s*['\"]([^'\"]+)['\"]")


def _read_browser(url: str, *, headless: bool) -> tuple[str, list[dict[str, str]]]:
    with sync_playwright() as playwright:
        options = {"headless": headless}
        options["channel"] = "chromium" if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else "msedge"
        browser = playwright.chromium.launch(**options)
        try:
            page = browser.new_page(locale="uk-UA")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            player = page.locator("#pre.playlists-ajax")
            if player.count():
                player.scroll_into_view_if_needed(timeout=20000)
                try:
                    page.locator("#pre.playlists-ajax .playlists-videos li[data-file]").first.wait_for(timeout=45000 if not headless else 18000)
                except Exception:
                    pass
            title = page.locator("h1").first.inner_text(timeout=10000) if page.locator("h1").count() else page.title()
            data = page.evaluate("""() => {
                const root = document.querySelector('#pre.playlists-ajax');
                const items = root ? [...root.querySelectorAll('.playlists-videos li[data-file]')] : [];
                if (items.length) return items.map((item, index) => ({
                    number: String(parseInt(item.textContent.match(/\\d+/)?.[0] || String(index + 1), 10)),
                    voice: item.dataset.voice || 'Невідоме озвучення',
                    url: new URL(item.dataset.file, location.href).href
                }));
                const iframe = root?.querySelector('iframe[src]') || document.querySelector('iframe#pre[src*="ashdi.vip/vod/"]');
                return iframe ? [{number:'1', voice:'Українська', url:new URL(iframe.src, location.href).href}] : [];
            }""")
            return title.strip(), data
        finally:
            browser.close()


async def discover(url: str) -> tuple[str, list[dict[str, str]]]:
    try:
        title, items = await asyncio.to_thread(_read_browser, url, headless=True)
    except Exception as error:
        raise RuntimeError(f"Не вдалося відкрити UAKINO в браузері: {error}") from error
    if items:
        return title, items
    title, items = await asyncio.to_thread(_read_browser, url, headless=False)
    if not items:
        raise RuntimeError("Список серій UAKINO недоступний. Перевірте сторінку в браузері та спробуйте знову.")
    return title, items


async def resolve(http: SourceHttp, player_url: str, page_url: str):
    html = await http.get_text(player_url, kind="media", referer=page_url)
    match = FILE_RE.search(html)
    if not match:
        raise RuntimeError("Плеєр UAKINO не повернув відеопотік.")
    return await inspect_master(http, match.group(1), player_url)


def episode_from_item(item: dict[str, str], season: int | None) -> Episode:
    player_url = item["url"]
    if not player_url.startswith("https://"):
        player_url = urljoin("https://ashdi.vip", player_url)
    player_url = validate_url(player_url, kind="media")
    return Episode(id=player_url, number=int(item["number"]), season=season,
                   voice=item["voice"], source_url=player_url)


def title_and_season(raw_title: str) -> tuple[str, int | None]:
    soup = BeautifulSoup(raw_title, "html.parser")
    clean = soup.get_text(" ", strip=True)
    match = re.search(r"\b(\d+)\s*сезон\b", clean, re.I)
    title = re.sub(r"\s*\d+\s*сезон.*$", "", clean, flags=re.I).strip()
    return title or clean, int(match.group(1)) if match else None

