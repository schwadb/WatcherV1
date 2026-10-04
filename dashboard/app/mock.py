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
    return alerts_src.parse(_load(settings, "alerts.json"), takeover_events=settings.cfg["weather"].get("takeover_events"))


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
    data = _load(settings, "stocks.json")
    # A few more made-up quotes so the scrolling tile grid can be seen without a Finnhub key.
    extra = [("AAPL", "Apple", 231.55, 1.84), ("MSFT", "Microsoft", 512.10, -3.22), ("NVDA", "Nvidia", 187.42, 5.61), ("AMZN", "Amazon", 221.08, -0.95)]
    for sym, name, price, change in extra:
        data["quotes"].append({"symbol": sym, "name": name, "price": price, "change": change, "change_pct": round(change / (price - change) * 100, 3),
                               "prev_close": round(price - change, 2), "high": price + 1, "low": price - 2, "quote_time": data["quotes"][0]["quote_time"]})
    return data


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


async def nowplaying(settings: Settings) -> dict[str, Any]:
    data = _load(settings, "nowplaying.json")
    data["progress_ms"] = (int(time.time() * 1000) % data["duration_ms"])
    data["progress_pct"] = round(data["progress_ms"] / data["duration_ms"] * 100, 1)
    return data


async def sports(settings: Settings) -> dict[str, Any]:
    # Parse the saved ESPN responses as of the day they were captured so "next/last" stay meaningful.
    team = sports_src.parse_team(
        _load(settings, "sports/team.json"), _load(settings, "sports/schedule.json"),
        now=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    team["league"] = "football/college-football"
    # A second, made-up team so the rotating tile can be seen without network access.
    other = dict(team, name="Kansas City Chiefs", short="Chiefs", abbr="KC", color="#e31837", logo="", league="football/nfl",
                 record="3-1", standing="1st in AFC West",
                 next=dict(team["next"], opponent="Las Vegas Raiders", opp_abbr="LV", home=False, tv="CBS"),
                 last=dict(team["last"], opponent="Baltimore Ravens", result="L 17-20", won=False))
    return {"teams": [team, other], "errors": []}
