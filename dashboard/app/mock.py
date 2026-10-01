"""Mock mode (DASHBOARD_MOCK=1): every source is served from fixtures/, no internet or keys needed."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .sources import alerts as alerts_src
from .sources import calendar as calendar_src
from .sources import news as news_src
from .sources import radar as radar_src
from .sources import sports as sports_src
from .sources import weather as weather_src


def _load(settings: Settings, name: str) -> Any:
    path = settings.fixtures_dir / name
    if name.endswith(".json"):
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_bytes()


async def weather(settings: Settings) -> dict[str, Any]:
    raw = _load(settings, "weather.json")
    # Shift the fixture's hourly block to "now" so the strip always shows upcoming hours.
    now = datetime.now()
    raw["current"]["time"] = now.strftime("%Y-%m-%dT%H:%M")
    hours = len(raw["hourly"]["time"])
    base = now.replace(minute=0, second=0, microsecond=0)
    raw["hourly"]["time"] = [(base.timestamp() + i * 3600) for i in range(hours)]
    raw["hourly"]["time"] = [datetime.fromtimestamp(t).strftime("%Y-%m-%dT%H:%M") for t in raw["hourly"]["time"]]
    return weather_src.parse(raw, settings, _load(settings, "air.json"))


async def alerts(settings: Settings) -> dict[str, Any]:
    # The fixture's Tornado Watch expires in 2099 (always active); its Wind Advisory is expired (always filtered).
    return alerts_src.parse(_load(settings, "alerts.json"))


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
    cals = [
        {"name": "Work", "color": "#5aa9ff", "file": "calendar.ics"},
        {"name": "Family", "color": "#f5b942", "file": "calendar2.ics"},
    ]
    events = []
    for cal in cals:
        events.extend(calendar_src.events_from_ics(_load(settings, cal["file"]), settings, None, cal))
    return {
        "days": calendar_src.group_by_day(events, settings),
        "count": len(events),
        "calendars": [{"name": c["name"], "color": c["color"], "ok": True, "error": None} for c in cals],
        "errors": [],
    }


async def news(settings: Settings) -> dict[str, Any]:
    items = news_src.parse_feed("Sample News", _load(settings, "news.xml"))
    return {"headlines": news_src.merge([items], int(settings.cfg["news"]["max_headlines"])), "errors": []}


async def sports(settings: Settings) -> dict[str, Any]:
    # Parse the saved ESPN responses as of the day they were captured so "next/last" stay meaningful.
    team = sports_src.parse_team(
        _load(settings, "sports/team.json"), _load(settings, "sports/schedule.json"),
        now=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    team["league"] = "football/college-football"
    return {"teams": [team], "errors": []}
