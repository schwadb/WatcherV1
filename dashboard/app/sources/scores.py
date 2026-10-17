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
}
DEFAULT_LEAGUES = ["football/nfl", "football/college-football", "basketball/nba", "baseball/mlb", "hockey/nhl", "basketball/mens-college-basketball"]
TTL_LIVE, TTL_IDLE = 30.0, 120.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def enabled_leagues(settings: Settings) -> list[str]:
    raw = (settings.cfg.get("scores") or {}).get("leagues")
    keys = [k for k in (raw or DEFAULT_LEAGUES) if k in LEAGUES]
    return keys or DEFAULT_LEAGUES


def league_list(settings: Settings) -> list[dict[str, str]]:
    return [{"key": k, "label": LEAGUES[k][2]} for k in enabled_leagues(settings)]


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
