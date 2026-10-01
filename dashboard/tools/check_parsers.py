"""Offline checks for the data parsers, using the files in fixtures/. No network needed.

Run:  .venv/bin/python tools/check_parsers.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings  # noqa: E402
from app.sources import alerts, astro, calendar, news, sports, weather  # noqa: E402

settings = load_settings()
FX = settings.fixtures_dir
checks: list[bool] = []


def check(label: str, ok: bool) -> None:
    checks.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + label)


def load(name: str):
    return json.loads((FX / name).read_text(encoding="utf-8"))


# ---- alerts ----------------------------------------------------------------------------------
a = alerts.parse(load("alerts.json"), now=datetime(2026, 10, 1, tzinfo=timezone.utc))
check("alerts: expired advisory is dropped", a["count"] == 1 and a["top"]["event"] == "Tornado Watch")
check("alerts: severity order puts Severe first", a["alerts"][0]["severity"] == "Severe")
check("alerts: all expired -> empty", alerts.parse(load("alerts.json"), now=datetime(2100, 1, 1, tzinfo=timezone.utc))["count"] == 0)

# ---- moon ------------------------------------------------------------------------------------
m0 = astro.moon_phase(datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc))
m_full = astro.moon_phase(datetime(2000, 1, 21, 4, 40, tzinfo=timezone.utc))
check("moon: reference new moon -> phase 0", m0["phase"] < 0.01 and m0["name"] == "New moon")
check("moon: ~14.8 days later -> full", m_full["name"] == "Full moon" and m_full["illumination"] > 97)

# ---- weather ---------------------------------------------------------------------------------
w = weather.parse(load("weather.json"), settings, load("air.json"))
check("weather: hourly strip has hourly_hours entries", len(w["hourly"]) == int(settings.cfg["weather"]["hourly_hours"]))
check("weather: hourly starts at the current hour", w["hourly"][0]["time"][:13] == w["current"]["time"][:13])
check("weather: UV label present", w["today"]["uv"] and w["today"]["uv"]["label"] in ("Low", "Moderate", "High", "Very high", "Extreme"))
check("weather: air quality parsed", w["air"] and w["air"]["label"] == "Good")
check("weather: air quality failure is non-fatal", weather.parse(load("weather.json"), settings, None)["air"] is None)
check("weather: moon included", "name" in w["moon"])

# ---- sports ----------------------------------------------------------------------------------
s = sports.parse_team(load("sports/team.json"), load("sports/schedule.json"), now=datetime(2026, 10, 1, tzinfo=timezone.utc))
check("sports: team + record", s["abbr"] == "NEB" and s["record"] == "4-0")
check("sports: next game is the first unplayed one", s["next"] and s["next"]["opp_abbr"] == "MD" and s["next"]["home"] is True)
check("sports: last game result string", s["last"] and s["last"]["result"] == "W 31-13" and s["last"]["won"] is True)
check("sports: no live game", s["live"] is None)
check("sports: config normalizes 'football/college-football'", sports.teams(type("S", (), {"cfg": {"sports": [{"league": "football/college-football", "team": "NEB"}]}})()) == [{"sport": "football", "league": "college-football", "team": "NEB"}])

# ---- calendars -------------------------------------------------------------------------------
now = datetime(2026, 9, 30, 8, 0, tzinfo=__import__("zoneinfo").ZoneInfo("America/Chicago"))
ev1 = calendar.events_from_ics((FX / "calendar.ics").read_bytes(), settings, now, {"name": "Work", "color": "#5aa9ff"})
ev2 = calendar.events_from_ics((FX / "calendar2.ics").read_bytes(), settings, now, {"name": "Family", "color": "#f5b942"})
days = calendar.group_by_day(ev1 + ev2, settings, now)
check("calendars: events carry their calendar color", all(e["color"] == "#f5b942" for e in ev2) and all(e["calendar"] == "Work" for e in ev1))
merged_titles = [e["title"] for d in days for e in d["events"]]
check("calendars: merged agenda mixes both", "Soccer practice" in merged_titles and "Team stand-up" in merged_titles)
sat = next(d for d in days if d["date"] == "2026-10-03")
check("calendars: yearly all-day birthday + weekly lesson on the right day", [e["title"] for e in sat["events"]][:1] == ["Piano lesson"] and any(e["title"] == "Grandma's birthday" for e in next(d for d in days if d["date"] == "2026-10-04")["events"]))
check("calendars: parse() wrapper still works", calendar.parse((FX / "calendar.ics").read_bytes(), settings, now)["count"] == len(ev1))

# ---- news ------------------------------------------------------------------------------------
items = news.parse_feed("Sample", (FX / "news.xml").read_bytes())
merged = news.merge([items, items], 40)
check("news: duplicates removed across feeds", len(merged) == 7)

print(f"\n{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
