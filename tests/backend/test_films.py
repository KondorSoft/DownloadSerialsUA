import asyncio

from app.sources import uaflix, uakino


def test_uaflix_film_page_creates_single_film():
    class Http:
        async def get_text(self, *args, **kwargs):
            return '<h1>Хітмен / Найманий вбивця дивитись онлайн</h1><iframe src="https://zetvideo.net/vod/6069"></iframe>'

    url = "https://uafix.net/films/najmanij-vbivcja/"
    title, season, episodes = asyncio.run(uaflix.discover(Http(), url))
    assert title == "Хітмен / Найманий вбивця"
    assert season is None
    assert len(episodes) == 1
    assert episodes[0].source_url == url
    assert episodes[0].season is None


def test_uakino_film_player_creates_single_film():
    title, season = uakino.title_and_season("Марті")
    episode = uakino.episode_from_item({"url": "https://ashdi.vip/vod/298569", "number": "1", "voice": "Українська"}, season)
    assert title == "Марті"
    assert episode.source_url == "https://ashdi.vip/vod/298569"
    assert episode.season is None
