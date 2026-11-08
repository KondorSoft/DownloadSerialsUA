from __future__ import annotations

import re
from urllib.parse import urljoin

from app.domain.models import Variant
from app.domain.security import validate_url
from app.adapters.outbound.sources.http import SourceHttp


ATTR_RE = re.compile(r'([A-Z-]+)=(?:"([^"]*)"|([^,]*))')
EXTINF_RE = re.compile(r"#EXTINF:([0-9.]+)")


def parse_attributes(line: str) -> dict[str, str]:
    return {match.group(1): match.group(2) if match.group(2) is not None else match.group(3) for match in ATTR_RE.finditer(line)}


async def inspect_master(http: SourceHttp, url: str, referer: str) -> list[Variant]:
    text = await http.get_text(url, kind="media", referer=referer)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries: list[tuple[str, dict[str, str]]] = []
    for index, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:") and index + 1 < len(lines):
            entries.append((urljoin(url, lines[index + 1]), parse_attributes(line)))
    if not entries and "#EXTINF:" in text:
        entries.append((url, {}))
    variants: list[Variant] = []
    for playlist_url, attrs in entries:
        validate_url(playlist_url, kind="media")
        media = text if playlist_url == url else await http.get_text(playlist_url, kind="media", referer=referer)
        if "#EXT-X-KEY" in media:
            continue
        duration = sum(float(item) for item in EXTINF_RE.findall(media))
        if duration <= 0:
            continue
        for line in media.splitlines():
            if line and not line.startswith("#"):
                validate_url(urljoin(playlist_url, line.strip()), kind="media")
        resolution = attrs.get("RESOLUTION", "0x0").split("x")
        width, height = int(resolution[0]), int(resolution[1])
        bandwidth = int(attrs.get("AVERAGE-BANDWIDTH") or attrs.get("BANDWIDTH") or 0)
        label = f"{height}p" if height else "Оригінал"
        variants.append(Variant(label=label, width=width, height=height, bandwidth=bandwidth,
                                duration_seconds=duration, estimated_bytes=round(duration * bandwidth / 8),
                                playlist_url=playlist_url, referer=referer))
    return sorted(variants, key=lambda variant: variant.height, reverse=True)
