import asyncio

import pytest

from app.security import normalize_source_url, validate_url
from app.sources.hls import inspect_master


def test_supported_pages_and_blocked_targets():
    assert normalize_source_url("https://uakino.best/seriesss/show.html").site == "UAKINO"
    assert normalize_source_url("https://uafix.net/serials/show/season-02-episode-01/").site == "UAFLIX"
    for value in ("http://uakino.best/x", "https://uakino.best.evil.test/x", "https://127.0.0.1/x", "https://uafix.net:8443/x"):
        with pytest.raises(ValueError):
            normalize_source_url(value)
    with pytest.raises(ValueError):
        validate_url("https://localhost/secret", kind="media")


def test_hls_qualities_and_estimates():
    class FakeHttp:
        async def get_text(self, url, *, kind, referer=None):
            if url.endswith("master.m3u8"):
                return "#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=1920x1080,BANDWIDTH=2000000\n1080.m3u8\n#EXT-X-STREAM-INF:RESOLUTION=1280x720,AVERAGE-BANDWIDTH=1000000,BANDWIDTH=1200000\n720.m3u8"
            return "#EXTM3U\n#EXTINF:5.0,\nhttps://ashdi.vip/seg1.ts\n#EXTINF:5.0,\nhttps://ashdi.vip/seg2.ts"

    variants = asyncio.run(inspect_master(FakeHttp(), "https://ashdi.vip/master.m3u8", "https://ashdi.vip/vod/1"))
    assert [variant.label for variant in variants] == ["1080p", "720p"]
    assert variants[0].estimated_bytes == 2_500_000
    assert variants[1].estimated_bytes == 1_250_000
