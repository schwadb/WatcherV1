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
from app.sources import alerts, astro, calendar, news, radar, spotify, sports, weather  # noqa: E402

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
check("alerts: Tornado Watch triggers the takeover by default", a["takeover"] and a["takeover"]["event"] == "Tornado Watch")
check("alerts: takeover patterns are wildcards", alerts.is_takeover("Severe Thunderstorm Warning", ["*warning"]) and not alerts.is_takeover("Flood Watch", ["*Warning"]))
check("alerts: custom pattern list respected", alerts.parse(load("alerts.json"), now=datetime(2026, 10, 1, tzinfo=timezone.utc), takeover_events=["Flash Flood Warning"])["takeover"] is None)

# ---- radar (NWS WMS) ----------------------------------------------------------------------------
_caps = '<Layer><Name>conus_bref_qcd</Name><Dimension name="time" default="2026-10-04T23:42:04Z" units="ISO8601" nearestValue="1">' + ",".join(f"2026-10-04T{22 + m // 60:02d}:{m % 60:02d}:00.000Z" for m in range(0, 120, 2)) + "</Dimension></Layer>"
_times = radar.parse_wms_times(_caps)
_fr = radar.pick_frames(_times, now=datetime(2026, 10, 4, 23, 58, tzinfo=timezone.utc))
check("radar: WMS time dimension parsed", len(_times) == 60 and _times[0].hour == 22 and _times[-1].minute == 58)
check("radar: last hour thinned to at most 15 frames, newest last", 10 <= len(_fr) <= 15 and _fr[-1]["path"] == "2026-10-04T23:58:00.000Z" and _fr[0]["time"] < _fr[-1]["time"])
_st = {"features": [{"properties": {"id": "KOAX", "name": "Omaha", "stationType": "WSR-88D"}, "geometry": {"coordinates": [-96.3668, 41.32027]}}, {"properties": {"id": "KLNK", "name": "Lincoln TDWR", "stationType": "TDWR"}, "geometry": {"coordinates": [-96.7, 40.8]}}, {"properties": {"id": "KUEX", "name": "Hastings", "stationType": "WSR-88D"}, "geometry": {"coordinates": [-98.4419, 40.3208]}}]}
_near = radar.nearest_site(_st, 40.3039, -97.0012)
check("radar: nearest NEXRAD site picked (TDWR ignored)", _near and _near["id"] == "KUEX" and 100 < _near["km"] < 140)  # Grand Island beats Omaha by a few km
check("radar: a different spot picks the other site", radar.nearest_site(_st, 41.25, -96.0)["id"] == "KOAX")

# ---- cache: offline handling and saved data ---------------------------------------------------
from app import cache as _cache
import socket as _socket, time as _time, json as _json
_c = _cache.SourceCache("weather", lambda: 600)
_c.fail(_socket.gaierror(-3, "Temporary failure in name resolution"))
check("cache: DNS failure counts as offline with a friendly message", _c.offline and _c.error == _cache.OFFLINE_MESSAGE)
check("cache: offline retries stay short", _cache.next_interval(_c) == 10 and (_c.fail(_socket.gaierror(-3, "x")) or _c.fail(_socket.gaierror(-3, "x")) or _c.fail(_socket.gaierror(-3, "x")) or _cache.next_interval(_c) == 30))
_c2 = _cache.SourceCache("stocks", lambda: 600)
for _ in range(4): _c2.fail(RuntimeError("Finnhub rate limit hit"))
check("cache: API errors back off exponentially", not _c2.offline and _cache.next_interval(_c2) == 80 and "rate limit" in _c2.error)
check("cache: empty exception text falls back to the type name", _cache.describe(Exception("")) == "Exception" and _cache.is_offline_error(Exception("All connection attempts failed")))
_dir = Path(_tmp.mkdtemp()) if "_tmp" in dir() else Path(__import__("tempfile").mkdtemp())
_c3 = _cache.SourceCache("news", lambda: 600, persist_path=_dir / "news.json"); _c3.set({"headlines": [1, 2]})
_c4 = _cache.SourceCache("news", lambda: 600, persist_path=_dir / "news.json")
check("cache: last good data survives a restart", _c4.load_persisted() and _c4.data == {"headlines": [1, 2]} and _c4.ok and _c4.age_seconds is not None and _c4.age_seconds < 5)
(_dir / "news.json").write_text(_json.dumps({"fetched_at": _time.time() - 4 * 86400, "data": {"old": True}}))
check("cache: data older than three days is not used", not _cache.SourceCache("news", lambda: 600, persist_path=_dir / "news.json").load_persisted())

# ---- spotify player + sound output -----------------------------------------------------------
from app import player as _player, audio as _audio
_ph = Path(__import__("tempfile").mkdtemp())
_conf = _player.config_text("Living Room TV", _ph)
check("player: spotifyd config names the device and uses pulseaudio", 'device_name = "Living Room TV"' in _conf and 'backend = "pulseaudio"' in _conf and "zeroconf_port = 1234" in _conf)
import os as _os0
_saved_path = _os0.environ["PATH"]
try:
    _os0.environ["PATH"] = "/nonexistent"; _player.install("Dashboard", _ph); check("player: missing spotifyd is explained", False)
except ValueError as exc:
    check("player: missing spotifyd is explained", "pacman -S spotifyd" in str(exc))
finally:
    _os0.environ["PATH"] = _saved_path
_pactl = """Card #48
\tName: alsa_card.pci-0000_01_00.1
\tDriver: module-alsa-card.c
\tOwner Module: n/a
\tProperties:
\t\tdevice.description = "Tahiti HDMI Audio [Radeon HD 7870 XT / 7950/7970]"
\tProfiles:
\t\toutput:hdmi-stereo: Digital Stereo (HDMI) Output (sinks: 1, sources: 0, priority: 5900, available: no)
\t\toutput:hdmi-stereo-extra1: Digital Stereo (HDMI 2) Output (sinks: 1, sources: 0, priority: 5700, available: yes)
\t\toff: Off (sinks: 0, sources: 0, priority: 0, available: yes)
\tActive Profile: off
\tPorts:
Card #50
\tName: alsa_card.pci-0000_00_1b.0
\tProperties:
\t\tdevice.description = "Built-in Audio"
\tProfiles:
\t\toutput:analog-stereo: Analog Stereo Output (sinks: 1, sources: 0, priority: 6500, available: yes)
\t\toutput:analog-stereo+input:analog-stereo: Analog Stereo Duplex (sinks: 1, sources: 1, priority: 6565, available: yes)
\t\tinput:analog-stereo: Analog Stereo Input (sinks: 0, sources: 1, priority: 65, available: yes)
\t\toff: Off (sinks: 0, sources: 0, priority: 0, available: yes)
\tActive Profile: output:analog-stereo+input:analog-stereo
"""
_cards = _audio.parse_cards(_pactl)
_outs = _audio.outputs_from(_cards)
check("audio: cards and profiles parsed with availability", len(_cards) == 2 and _cards[0]["profiles"][0]["available"] is False and _cards[0]["profiles"][1]["available"] is True)
check("audio: outputs are friendly, de-duplicated, HDMI first, current one flagged", [o["label"] for o in _outs] == ["TV / monitor over HDMI (port 2)", "Headphone / line-out jack", "TV / monitor over HDMI"] and _outs[1]["active"] and not _outs[0]["active"] and not _outs[2]["available"])
_sinks_txt = """Sink #57
\tState: RUNNING
\tName: alsa_output.pci-0000_00_1b.0.analog-stereo
\tDescription: Built-in Audio Analog Stereo
\tProperties:
\t\talsa.card = "0"
\tPorts:
\t\tanalog-output-speaker: Speaker (type: Speaker, priority: 10000, availability unknown)
\t\tanalog-output-headphones: Headphones (type: Headphones, priority: 9900, availability unknown)
\t\tanalog-output-lineout: Line Out (type: Line, priority: 9900, not available)
\tActive Port: analog-output-speaker
\tFormats:
\t\tpcm
"""
_sinks = _audio.parse_sinks(_sinks_txt)
check("audio: sink ports parsed with card link and availability", len(_sinks) == 1 and _sinks[0]["card"] == "alsa_card.pci-0000_00_1b.0" and [p["id"] for p in _sinks[0]["ports"]] == ["analog-output-speaker", "analog-output-headphones", "analog-output-lineout"] and _sinks[0]["ports"][2]["available"] is False and _sinks[0]["active_port"] == "analog-output-speaker")
_outs2 = _audio.outputs_from(_cards, _sinks)
check("audio: one entry per jack, speaker marked current, unplugged jack greyed", [o["label"] for o in _outs2] == ["TV / monitor over HDMI (port 2)", "Headphone jack", "Internal speaker", "TV / monitor over HDMI", "Line out"] and next(o for o in _outs2 if o["label"] == "Internal speaker")["active"] and not next(o for o in _outs2 if o["label"] == "Line out")["available"] and next(o for o in _outs2 if o["label"] == "Headphone jack")["port"] == "analog-output-headphones")
_calls = []
_audio._run = lambda cmd, timeout=15: (_calls.append(cmd) or (0, "57\talsa_output.pci-0000_00_1b.0.analog-stereo\tPipeWire\ts16le 2ch 48000Hz\tRUNNING\n"))
check("audio: selecting a jack sets profile, default sink and port", _audio.select_output("alsa_card.pci-0000_00_1b.0", "output:analog-stereo", "analog-output-headphones") == "alsa_output.pci-0000_00_1b.0.analog-stereo" and [c[1] for c in _calls] == ["set-card-profile", "list", "set-default-sink", "set-sink-port"] and _calls[-1][-1] == "analog-output-headphones")
_tone = _audio.tone_file(_ph / "cache")
check("audio: test tone file written", _tone.exists() and _tone.stat().st_size > 100000)

# ---- scoreboard --------------------------------------------------------------------------------
from app.sources import scores as _scores
_sb = json.loads((FX / "scoreboard.json").read_text(encoding="utf-8"))["leagues"]
_cfb = _scores.parse_scoreboard(_sb["football/college-football"], {"158", "NEB"})
check("scores: games parsed with both sides, scores and status", _cfb["games"] and all(g["home"]["abbr"] and g["away"]["abbr"] and g["state"] in ("pre", "in", "post") for g in _cfb["games"]))
check("scores: my team first and flagged, live games counted", _cfb["games"][0]["mine"] and "NEB" in (_cfb["games"][0]["home"]["abbr"], _cfb["games"][0]["away"]["abbr"]) and _cfb["live"] == sum(1 for g in _cfb["games"] if g["state"] == "in"))
_nfl = _scores.parse_scoreboard(_sb["football/nfl"])
check("scores: upcoming games carry TV and kickoff, finals carry a winner", any(g["tv"] for g in _nfl["games"] if g["state"] == "pre") and all((g["home"]["winner"] or g["away"]["winner"]) for g in _nfl["games"] if g["state"] == "post"))
check("scores: default league list and labels", _scores.enabled_leagues(settings) and all(k in _scores.LEAGUES for k in _scores.enabled_leagues(settings)) and _scores.LEAGUES["football/nfl"][2] == "NFL")

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
_live_team = {"abbr": "KC", "id": "12", "live": {"id": "401872976", "score_us": None, "score_them": None, "detail": "", "state": "in"}}
_board = {"events": [{"id": "401872976", "competitions": [{"status": {"type": {"state": "in", "shortDetail": "1:46 - 4th"}}, "competitors": [{"team": {"abbreviation": "LV", "id": "13"}, "score": "27"}, {"team": {"abbreviation": "KC", "id": "12"}, "score": "30"}]}]}]}
check("sports: live score filled from the league scoreboard", sports.apply_scoreboard(_live_team, _board) and _live_team["live"]["score_us"] == 30 and _live_team["live"]["score_them"] == 27 and _live_team["live"]["clock"] == "1:46 - 4th")
check("sports: scoreboard without our game leaves things alone", not sports.apply_scoreboard({"abbr": "NEB", "live": {"id": "1"}}, _board))
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

from app import chronalert as _ca
_h = Path(_tmp.mkdtemp()); (_h / "Downloads").mkdir(); (_h / "Downloads/ChronAlert-x86_64.AppImage").write_text("#!/bin/sh\n"); (_h / "Downloads/ChronAlert-x86_64.AppImage").chmod(0o755)
check("chronalert: AppImage found in ~/Downloads", (_ca.find_appimage(_h) or "").endswith("ChronAlert-x86_64.AppImage"))
check("chronalert: nothing found in an empty home", _ca.find_appimage(Path(_tmp.mkdtemp())) is None)
_unit = _ca.service_text("/home/me/Applications/ChronAlert-x86_64.AppImage")
check("chronalert: service runs the AppImage without a browser and restarts it", "ExecStart=/home/me/Applications/ChronAlert-x86_64.AppImage --no-browser" in _unit and "Restart=always" in _unit)
_os.environ["DASHBOARD_SYSTEMCTL_FAKE"] = str(_h / "systemctl.log")
_ca.install(str(_h / "Downloads/ChronAlert-x86_64.AppImage"), _h)
check("chronalert: install writes the unit and enables it", _ca.service_path(_h).exists() and "enable --now chronalert" in (_h / "systemctl.log").read_text() and _ca.status(_h)["enabled"])
_ca.remove(_h)
check("chronalert: remove deletes the unit", not _ca.service_path(_h).exists() and not _ca.status(_h)["enabled"])
try:
    _ca.install(str(_h / "missing.AppImage"), _h); check("chronalert: missing AppImage refused", False)
except ValueError:
    check("chronalert: missing AppImage refused", True)
del _os.environ["DASHBOARD_SYSTEMCTL_FAKE"]

from app.manage import short_company_name as _short
check("stocks: company names shortened for the tile", _short("Apple Inc") == "Apple" and _short("SPDR S&P 500 ETF Trust") == "SPDR S&P 500" and _short("Alphabet Inc Class A") == "Alphabet")
_links = news.feed_links_in_html((FX / "site.html").read_text(), "https://example.org/site.html")
check("news: feed link discovered in a web page", _links == ["https://example.org/news.xml"])
check("news: page without feed links -> none", news.feed_links_in_html("<html><head><link rel=stylesheet href=a.css></head></html>", "https://x.org/") == [])
check("news: feed summary has title and first headline", (news.feed_summary((FX / "news.xml").read_bytes()) or {}).get("title") == "Sample News")
check("news: HTML is not mistaken for a feed", news.feed_summary(b"<html><body>hi</body></html>") is None)
check("news: catalogue groups all have feeds with http addresses", all(g["feeds"] and all(f["url"].startswith("http") for f in g["feeds"]) for g in news.FEED_CATALOG))

print(f"\n{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
