"""League scoreboards (every game today) from ESPN's public site API, for the Scores panel.

Fetched on demand, cached briefly, never polled in the background. Your own teams (Settings ->
Sports teams) are listed first and flagged `mine`.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import Settings
from .sports import HEADERS, teams as my_teams

SCOREBOARD = "https://site.web.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
# key -> (sport, league, label, extra query params)
LEAGUES: dict[str, tuple[str, str, str, dict[str, str]]] = {
    "football/nfl": ("football", "nfl", "NFL", {}),
    "football/college-football": ("football", "college-football", "College FB", {"groups": "80", "limit": "200"}),
    "basketball/nba": ("basketball", "nba", "NBA", {}),
    "basketball/mens-college-basketball": ("basketball", "mens-college-basketball", "College BB", {"groups": "50", "limit": "300"}),
    "baseball/mlb": ("baseball", "mlb", "MLB", {}),
    "hockey/nhl": ("hockey", "nhl", "NHL", {}),
    "basketball/wnba": ("basketball", "wnba", "WNBA", {}),
    "soccer/usa.1": ("soccer", "usa.1", "MLS", {}),
    "baseball/college-baseball": ("baseball", "college-baseball", "College baseball", {"limit": "300"}),
    "volleyball/womens-college-volleyball": ("volleyball", "womens-college-volleyball", "College volleyball", {"limit": "300"}),
}
# Nebraska high school scores from the NSAA (the state association's own weekly score pages).
NSAA_URL = "https://secure.nsaahome.org/calculate/wildcard/weeks.php"
NSAA_SPORTS: dict[str, str] = {
    "nsaa/fb": "HS football", "nsaa/vb": "HS volleyball", "nsaa/bb": "HS boys basketball", "nsaa/gb": "HS girls basketball",
    "nsaa/wr": "HS wrestling", "nsaa/sb": "HS softball", "nsaa/bsb": "HS baseball", "nsaa/soc": "HS soccer",
}
DEFAULT_LEAGUES = ["football/nfl", "football/college-football", "basketball/nba", "baseball/mlb", "hockey/nhl", "basketball/mens-college-basketball",
                   "volleyball/womens-college-volleyball", "baseball/college-baseball", "nsaa/fb", "nsaa/vb", "nsaa/bb", "nsaa/gb", "nsaa/wr"]
ALL_KEYS = list(LEAGUES) + list(NSAA_SPORTS)


def label_for(key: str) -> str:
    return LEAGUES[key][2] if key in LEAGUES else NSAA_SPORTS.get(key, key)
TTL_LIVE, TTL_IDLE = 30.0, 120.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def enabled_leagues(settings: Settings) -> list[str]:
    raw = (settings.cfg.get("scores") or {}).get("leagues")
    keys = [k for k in (raw or DEFAULT_LEAGUES) if k in ALL_KEYS]
    return keys or DEFAULT_LEAGUES


def league_list(settings: Settings) -> list[dict[str, str]]:
    return [{"key": k, "label": label_for(k)} for k in enabled_leagues(settings)]


def high_schools(settings: Settings) -> list[str]:
    raw = (settings.cfg.get("scores") or {}).get("high_schools") or []
    if isinstance(raw, str):
        raw = raw.split(",")
    return [str(x).strip() for x in raw if str(x).strip()]


def _side(c: dict[str, Any]) -> dict[str, Any]:
    t = c.get("team") or {}
    rec = (c.get("records") or [{}])[0].get("summary") if c.get("records") else ""
    rank = (c.get("curatedRank") or {}).get("current")
    score = c.get("score")
    try:
        score_n = int(float(score)) if score not in (None, "") else None
    except (TypeError, ValueError):
        score_n = None
    return {
        "id": str(t.get("id") or ""), "abbr": t.get("abbreviation") or "", "name": t.get("shortDisplayName") or t.get("displayName") or t.get("abbreviation") or "",
        "logo": t.get("logo"), "color": f"#{t['color']}" if t.get("color") else None, "score": score_n, "record": rec or "",
        "rank": rank if isinstance(rank, int) and rank <= 25 else None, "winner": c.get("winner") is True,
        "lines": [int(v) if isinstance(v, (int, float)) else v for v in (x.get("value") for x in c.get("linescores") or []) if v is not None],
    }


def parse_game(ev: dict[str, Any], mine: set[str]) -> dict[str, Any] | None:
    comp = (ev.get("competitions") or [{}])[0]
    comps = comp.get("competitors") or []
    home = next((c for c in comps if c.get("homeAway") == "home"), None)
    away = next((c for c in comps if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None
    status = (comp.get("status") or {}).get("type") or {}
    bc = comp.get("broadcasts") or []
    tv = ", ".join((bc[0].get("names") or [])[:2]) if bc else ""
    sit = comp.get("situation") or {}
    h, a = _side(home), _side(away)
    is_mine = bool({h["id"], h["abbr"].upper(), a["id"], a["abbr"].upper()} & mine)
    return {
        "id": str(ev.get("id") or ""), "date": comp.get("date") or ev.get("date"), "state": status.get("state") or "pre",
        "detail": status.get("shortDetail") or status.get("detail") or "", "completed": bool(status.get("completed")),
        "tv": tv, "venue": ((comp.get("venue") or {}).get("fullName")) or "",
        "odds": ((comp.get("odds") or [{}])[0].get("details")) or "" if comp.get("odds") else "",
        "situation": {"down": sit.get("downDistanceText") or "", "possession": str(sit.get("possession") or ""), "red_zone": bool(sit.get("isRedZone"))},
        "home": h, "away": a, "mine": is_mine,
    }


def parse_scoreboard(raw: dict[str, Any], mine: set[str] | None = None) -> dict[str, Any]:
    mine = mine or set()
    games = [g for g in (parse_game(ev, mine) for ev in raw.get("events") or []) if g]
    order = {"in": 0, "pre": 1, "post": 2}
    games.sort(key=lambda g: (not g["mine"], order.get(g["state"], 3), g["date"] or ""))
    week = (raw.get("week") or {}).get("number")
    return {"games": games, "week": week, "live": sum(1 for g in games if g["state"] == "in"), "fetched_at": datetime.now(timezone.utc).isoformat()}


def mine_for(settings: Settings, key: str) -> set[str]:
    """Team ids/abbreviations the user follows in this league (both forms, since config may hold either)."""
    out: set[str] = set()
    for t in my_teams(settings):
        if f"{t['sport']}/{t['league']}" == key:
            out.add(str(t["team"]).upper())
    return out


async def fetch_league(client: httpx.AsyncClient, settings: Settings, key: str) -> dict[str, Any]:
    if key not in LEAGUES:
        raise ValueError("unknown league")
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < (TTL_LIVE if cached[1].get("live") else TTL_IDLE):
        return cached[1]
    sport, league, label, params = LEAGUES[key]
    resp = await client.get(SCOREBOARD.format(sport=sport, league=league), params=params or None, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = parse_scoreboard(resp.json(), mine_for(settings, key))
    data.update(league=key, label=label)
    _cache[key] = (time.time(), data)
    return data


# ---- Nebraska high school (NSAA weekly score pages) -------------------------------------------
import html as _html
import re as _re

_TAGS = _re.compile(r"<script.*?</script>|<style.*?</style>", _re.S)
_DAY = _re.compile(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*\((\d{2})/(\d{2})/(\d{4})\)")
_SCORE = _re.compile(r"^(.+?)\s+(\d+),\s+(.+?)\s+(\d+)(?:\s*\((.*?)\))?\s*$")          # Elkhorn 35, Ralston 13 (Forfeit)
_VB = _re.compile(r"^(.+?)\s+def\.\s+(.+?),\s*([\d\-,\s]+?)\s*\((\d+)-(\d+)\)\s*$")   # Amherst def. Overton, 25-15, 25-11  (2-0)
_PENDING = _re.compile(r"^(\d{2})/(\d{2})/(\d{4}):\s+(.+?)\s+@\s+(.+?)(\s+--\s+(.*))?$")  # 10/16/2026: David City @ Tekamah-Herman -- CANCELLED


def _hs_side(name: str, score: int | None, winner: bool | None) -> dict[str, Any]:
    return {"id": name, "abbr": name, "name": name, "logo": None, "color": None, "score": score, "record": "", "rank": None, "winner": bool(winner), "lines": []}


def _mine_hs(names: list[str], schools: list[str]) -> bool:
    wanted = [x.lower() for x in schools]
    return any(any(w in n.lower() for w in wanted) for n in names) if wanted else False


def parse_nsaa(html_text: str, schools: list[str] | None = None) -> dict[str, Any]:
    """The NSAA 'Complete <Sport> Scores for Week N' page -> games in the scoreboard shape."""
    schools = schools or []
    text = _html.unescape(_re.sub(r"<[^>]+>", "\n", _TAGS.sub("", html_text)))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    games: list[dict[str, Any]] = []
    week = ""
    day = ""
    section = ""
    for line in lines:
        m = _re.match(r"Complete .*? Scores for Week\s*(.*)$", line)
        if m:
            week = m.group(1).strip()
            continue
        if line.startswith("This report was generated"):
            continue
        if line.startswith("Missing Scores"):
            section = "missing"; continue
        if line.startswith("Postponed/Cancelled"):
            section = "cancelled"; continue
        if "scores are not available" in line:
            break
        d = _DAY.match(line)
        if d:
            section = "scores"; day = f"{d.group(4)}-{d.group(2)}-{d.group(3)}"; continue
        if section in ("missing", "cancelled"):
            pm = _PENDING.match(line)
            if pm:
                date = f"{pm.group(3)}-{pm.group(1)}-{pm.group(2)}"
                note = (pm.group(7) or "").strip()
                cancelled = section == "cancelled" or "CANCEL" in note.upper() or "POSTPON" in note.upper()
                games.append({"id": f"nsaa-{date}-{pm.group(4)}-{pm.group(5)}", "date": date + "T00:00:00", "state": "post" if cancelled else "pre",
                              "detail": note.title() if note else ("Cancelled" if cancelled else "No score reported yet"), "completed": cancelled, "tv": "", "venue": "", "odds": "",
                              "situation": {"down": "", "possession": "", "red_zone": False},
                              "home": _hs_side(pm.group(5), None, None), "away": _hs_side(pm.group(4), None, None), "mine": _mine_hs([pm.group(4), pm.group(5)], schools)})
            continue
        vm = _VB.match(line)
        if vm:
            sets = vm.group(3).strip().rstrip(",")
            games.append({"id": f"nsaa-{day}-{vm.group(1)}-{vm.group(2)}", "date": day + "T00:00:00", "state": "post", "detail": f"Final · {sets}", "completed": True, "tv": "", "venue": "", "odds": "",
                          "situation": {"down": "", "possession": "", "red_zone": False},
                          "home": _hs_side(vm.group(2), int(vm.group(5)), False), "away": _hs_side(vm.group(1), int(vm.group(4)), True), "mine": _mine_hs([vm.group(1), vm.group(2)], schools)})
            continue
        sm = _SCORE.match(line)
        if sm and section == "scores":
            a, sa, b, sb, note = sm.group(1), int(sm.group(2)), sm.group(3), int(sm.group(4)), (sm.group(5) or "")
            games.append({"id": f"nsaa-{day}-{a}-{b}", "date": day + "T00:00:00", "state": "post", "detail": "Final" + (f" · {note}" if note else ""), "completed": True, "tv": "", "venue": "", "odds": "",
                          "situation": {"down": "", "possession": "", "red_zone": False},
                          "home": _hs_side(b, sb, sb > sa), "away": _hs_side(a, sa, sa >= sb), "mine": _mine_hs([a, b], schools)})
    order = {"in": 0, "pre": 1, "post": 2}
    games.sort(key=lambda g: (not g["mine"], order.get(g["state"], 3), g["date"] or "", g["away"]["name"]))
    return {"games": games, "week": week or None, "live": 0, "fetched_at": datetime.now(timezone.utc).isoformat(), "note": "Scores as reported to the NSAA; final scores only, no live updates." if games else "No games reported this week."}


async def fetch_nsaa(client: httpx.AsyncClient, settings: Settings, key: str) -> dict[str, Any]:
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]
    resp = await client.get(NSAA_URL, params={"sport": key.split("/", 1)[1]}, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    data = parse_nsaa(resp.text, high_schools(settings))
    data.update(league=key, label=NSAA_SPORTS[key])
    _cache[key] = (time.time(), data)
    return data


async def fetch_any(client: httpx.AsyncClient, settings: Settings, key: str) -> dict[str, Any]:
    return await fetch_nsaa(client, settings, key) if key in NSAA_SPORTS else await fetch_league(client, settings, key)


async def fetch_all(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    """Every enabled league at once; a league that fails just reports its error."""
    import asyncio

    keys = enabled_leagues(settings)
    results = await asyncio.gather(*(fetch_any(client, settings, k) for k in keys), return_exceptions=True)
    sections, games, errors = [], [], []
    for key, res in zip(keys, results):
        if isinstance(res, BaseException):
            errors.append(f"{label_for(key)}: {res}")
            continue
        sections.append({"key": key, "label": label_for(key), "count": len(res["games"]), "live": res.get("live", 0)})
        for g in res["games"]:
            games.append({**g, "league": key, "league_label": label_for(key)})
    order = {"in": 0, "pre": 1, "post": 2}
    games.sort(key=lambda g: (not g["mine"], order.get(g["state"], 3), g["date"] or ""))
    return {"league": "all", "label": "All", "games": games, "sections": sections, "errors": errors, "live": sum(1 for g in games if g["state"] == "in"), "week": None, "fetched_at": datetime.now(timezone.utc).isoformat()}
