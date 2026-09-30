"""Mock mode (DASHBOARD_MOCK=1): every source is served from fixtures/, no internet or keys needed."""
from __future__ import annotations

import json
import time
from typing import Any

from .config import Settings
from .sources import calendar as calendar_src
from .sources import news as news_src
from .sources import radar as radar_src
from .sources import weather as weather_src


def _load(settings: Settings, name: str) -> Any:
    path = settings.fixtures_dir / name
    if name.endswith(".json"):
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_bytes()


async def weather(settings: Settings) -> dict[str, Any]:
    return weather_src.parse(_load(settings, "weather.json"), settings)


async def radar(settings: Settings) -> dict[str, Any]:
    now = int(time.time())
    data = radar_src.parse_rainviewer(_load(settings, "radar.json"), settings)
    # Point every tile at a local placeholder so the map renders offline.
    n = len(data["frames"])
    data["frames"] = [{"time": now - (n - 1 - i) * 600, "path": f"/f{i}"} for i in range(n)]
    data["tile_template"] = "/static/mock/radar{path}.png?z={z}&x={x}&y={y}"
    data["basemap_template"] = "/static/mock/basemap.png?z={z}&x={x}&y={y}"
    data["labels_template"] = ""
    return data


async def stocks(settings: Settings) -> dict[str, Any]:
    return _load(settings, "stocks.json")


async def calendar(settings: Settings) -> dict[str, Any]:
    return calendar_src.parse(_load(settings, "calendar.ics"), settings)


async def news(settings: Settings) -> dict[str, Any]:
    items = news_src.parse_feed("Sample News", _load(settings, "news.xml"))
    return {"headlines": news_src.merge([items], int(settings.cfg["news"]["max_headlines"])), "errors": []}
