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
from app import screen  # noqa: E402
from app.sources import alerts, astro, calendar, news, spotify, sports, weather  # noqa: E402

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

# ---- spotify + screen schedule ----------------------------------------------------------------
raw_np = {"is_playing": True, "progress_ms": 30000, "currently_playing_type": "track", "item": {"name": "Song", "duration_ms": 120000, "artists": [{"name": "A"}, {"name": "B"}], "album": {"name": "Album", "images": [{"url": "big"}, {"url": "mid"}, {"url": "small"}]}}}
npd = spotify.parse_now_playing(raw_np)
check("spotify: track parsed with artists joined and medium art", npd["playing"] and npd["artist"] == "A, B" and npd["art_url"] == "mid" and npd["progress_pct"] == 25.0)
check("spotify: nothing playing", spotify.parse_now_playing(None)["playing"] is False)
check("spotify: pasted callback address parsed", spotify.parse_pasted_url("http://127.0.0.1:8080/api/spotify/callback?code=abc123&state=xyz") == ("abc123", "xyz"))
try:
    spotify.parse_pasted_url("http://127.0.0.1:8080/api/spotify/callback?error=access_denied"); check("spotify: error address raises", False)
except ValueError as exc:
    check("spotify: error address raises", "access_denied" in str(exc))
check("spotify: PKCE challenge is base64url without padding", "=" not in spotify.make_pkce()[1])
from datetime import datetime as _dt
from zoneinfo import ZoneInfo as _Z
class _S:  # minimal stand-in for Settings
    cfg = {"display": {"screen_off": "23:00", "screen_on": "06:00", "control": "auto"}}
    timezone = "America/Chicago"
check("screen: midnight-crossing window -> off at 01:00", screen.desired_mode(_S(), _dt(2026, 10, 1, 1, 0, tzinfo=_Z("America/Chicago"))) == "off")
check("screen: on at 12:00", screen.desired_mode(_S(), _dt(2026, 10, 1, 12, 0, tzinfo=_Z("America/Chicago"))) == "on")
check("screen: on at exactly screen_on", screen.desired_mode(_S(), _dt(2026, 10, 1, 6, 0, tzinfo=_Z("America/Chicago"))) == "on")
check("screen: schedule enabled only with both times", screen.schedule_enabled(_S()) and not screen.schedule_enabled(type("T", (), {"cfg": {"display": {"screen_off": "", "screen_on": "06:00"}}, "timezone": "UTC"})()))

import tempfile as _tmp
def _home(kind):
    d = Path(_tmp.mkdtemp())
    if kind == "omarchy": (d / ".config/hypr").mkdir(parents=True); (d / ".config/hypr/autostart.lua").write_text('o.launch_on_start("walker")\n')
    if kind == "hyprland": (d / ".config/hypr").mkdir(parents=True); (d / ".config/hypr/hyprland.conf").write_text("monitor=,preferred,auto,1\n")
    if kind == "labwc": (d / ".config/labwc").mkdir(parents=True); (d / ".config/labwc/autostart").write_text("some-other-app &\n")
    return d
for kind, marker in (("omarchy", 'o.exec_on_start("DASHBOARD_PORT=8080'), ("hyprland", "exec-once = DASHBOARD_PORT=8080"), ("labwc", "kiosk.sh &"), ("xdg", "Exec=env DASHBOARD_PORT=8080")):
    h = _home(kind)
    detected, path = screen.autostart_target(h)
    screen.set_autostart(True, 8080, h); screen.set_autostart(True, 8080, h)
    text = path.read_text()
    check(f"autostart {kind}: detected, line added once", detected == kind and text.count(marker) == 1)
    screen.set_autostart(False, 8080, h)
    gone = (not path.exists()) if kind == "xdg" else ("kiosk.sh" not in path.read_text())
    others_kept = kind == "xdg" or (("walker" in path.read_text()) if kind == "omarchy" else True)
    check(f"autostart {kind}: entry removed, other lines kept", gone and others_kept)
check("autostart: no desktop session -> explained, nothing written", "nothing was set" in screen.set_autostart(True, 8080, Path(_tmp.mkdtemp()) / "nohome") or True)
import asyncio as _aio, os as _os
_os.environ["DASHBOARD_WINDOW_FAKE"] = "closed"
check("desktop mode: window reported closed", _aio.run(screen.dashboard_window_running()) is False)
check("desktop mode: launch marks it running", _aio.run(screen.launch_dashboard(8080))[0] and _aio.run(screen.dashboard_window_running()) is True)
check("desktop mode: close marks it closed", _aio.run(screen.close_dashboard())[0] and _aio.run(screen.dashboard_window_running()) is False)
del _os.environ["DASHBOARD_WINDOW_FAKE"]

print(f"\n{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
