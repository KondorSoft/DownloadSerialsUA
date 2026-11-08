from __future__ import annotations

from urllib.parse import urljoin
import httpx

from app.domain.security import validate_url


class SourceHttp:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=25, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0"})

    async def close(self) -> None:
        await self.client.aclose()

    async def get_text(self, url: str, *, kind: str, referer: str | None = None) -> str:
        current = validate_url(url, kind=kind)
        for _ in range(6):
            response = await self.client.get(current, headers={"Referer": referer} if referer else None)
            if response.status_code in (301, 302, 303, 307, 308):
                current = validate_url(urljoin(current, response.headers["location"]), kind=kind)
                continue
            response.raise_for_status()
            return response.text
        raise ValueError("Забагато переадресацій від відеосервісу.")
