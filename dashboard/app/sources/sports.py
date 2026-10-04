"""Favorite-team tile from ESPN's public (unofficial) site API: record, next game, last result, live score."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import Settings

# The site.api.espn.com host blocks some networks; site.web.api.espn.com serves the same data.
BASE = "https://site.web.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WatcherDashboard/1.0)"}
LIVE_INTERVAL = 120


def teams(settings: Settings) -> list[dict[str, str]]:
    """Normalize config: `sports: {teams: [...]}` or a bare list `sports: [...]`."""
    raw = settings.cfg.get("sports")
    entries = raw if isinstance(raw, list) else (raw or {}).get("teams") or []
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        league = str(e.get("league") or "").strip().strip("/")
        sport = str(e.get("sport") or "").strip()
        if "/" in league and not sport:  # allow "football/college-football"
            sport, league = league.split("/", 1)
        team = str(e.get("team") or e.get("team_id") or "").strip()
        if sport and league and team:
            out.append({"sport": sport, "league": league, "team": team})
    return out


def refresh_minutes(settings: Settings) -> float:
    raw = settings.cfg.get("sports")
    if isinstance(raw, dict):
        return float(raw.get("refresh_minutes", 10))
    return 10.0


def interval_seconds(settings: Settings, cache: Any) -> float:
    data = getattr(cache, "data", None) or {}
    if any(t.get("live") for t in data.get("teams", [])):
        return LIVE_INTERVAL
    return refresh_minutes(settings) * 60


def _score(competitor: dict[str, Any]) -> int | None:
    score = competitor.get("score")
    if isinstance(score, dict):
        score = score.get("value", score.get("displayValue"))
    try:
        return int(float(score)) if score not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _game(event: dict[str, Any], team_id: str) -> dict[str, Any] | None:
    comps = (event.get("competitions") or [{}])[0]
    competitors = comps.get("competitors") or []
    us = next((c for c in competitors if str((c.get("team") or {}).get("id")) == str(team_id)), None)
    them = next((c for c in competitors if c is not us), None)
    if not us or not them:
        return None
    status = (comps.get("status") or {}).get("type") or {}
    opp_team = them.get("team") or {}
    broadcasts = comps.get("broadcasts") or []
    tv = ""
    if broadcasts:
        media = broadcasts[0].get("media") or {}
        tv = media.get("shortName") or (broadcasts[0].get("names") or [""])[0]
    return {
        "id": str(event.get("id") or ""),
        "date": comps.get("date") or event.get("date"),
        "time_tbd": comps.get("timeValid") is False,
        "home": us.get("homeAway") == "home",
        "opponent": opp_team.get("shortDisplayName") or opp_team.get("displayName") or opp_team.get("abbreviation") or "?",
        "opp_abbr": opp_team.get("abbreviation") or "",
        "opp_logo": opp_team.get("logo") or ((opp_team.get("logos") or [{}])[0].get("href")),
        "venue": ((comps.get("venue") or {}).get("fullName")) or "",
        "tv": tv,
        "state": status.get("state") or "pre",  # pre | in | post
        "completed": bool(status.get("completed")),
        "detail": status.get("shortDetail") or status.get("detail") or "",
        "score_us": _score(us),
        "score_them": _score(them),
        "won": us.get("winner") if us.get("winner") is not None else None,
        "short_name": event.get("shortName") or event.get("name") or "",
    }


def parse_team(team_raw: dict[str, Any], schedule_raw: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    team = team_raw.get("team") or {}
    team_id = str(team.get("id"))
    record = ""
    for item in (team.get("record") or {}).get("items") or []:
        if item.get("type") in ("total", None):
            record = item.get("summary") or ""
            break
    logos = team.get("logos") or []
    games = [g for g in (_game(e, team_id) for e in schedule_raw.get("events") or []) if g]
    games.sort(key=lambda g: g["date"] or "")
    live = next((g for g in games if g["state"] == "in"), None)
    last = next((g for g in reversed(games) if g["state"] == "post"), None)
    upcoming = next((g for g in games if g["state"] == "pre"), None)
    if upcoming is None and team.get("nextEvent"):
        upcoming = _game(team["nextEvent"][0], team_id)
    if last:
        s_us, s_them = last["score_us"], last["score_them"]
        won = last["won"] if last["won"] is not None else (s_us is not None and s_them is not None and s_us > s_them)
        last["won"] = bool(won)
        last["result"] = f"{'W' if won else 'L'} {s_us}-{s_them}" if s_us is not None else ("W" if won else "L")
    if live:
        live["clock"] = live.get("detail")
    return {
        "name": team.get("displayName") or team.get("name") or "",
        "short": team.get("shortDisplayName") or team.get("nickname") or team.get("name") or "",
        "abbr": team.get("abbreviation") or "",
        "color": f"#{team['color']}" if team.get("color") else None,
        "logo": logos[0].get("href") if logos else None,
        "record": record,
        "standing": team.get("standingSummary") or "",
        "next": upcoming,
        "last": last,
        "live": live,
    }


SCOREBOARD = "https://site.web.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
SCOREBOARD_PARAMS = {"football/college-football": {"groups": "80", "limit": "200"}}  # all of FBS, not just the top 25


def apply_scoreboard(team: dict[str, Any], scoreboard: dict[str, Any]) -> bool:
    """Fill a live game's score and clock from the league scoreboard (the schedule feed leaves them empty)."""
    live = team.get("live")
    if not live:
        return False
    for event in scoreboard.get("events") or []:
        if str(event.get("id")) != live.get("id"):
            continue
        comps = (event.get("competitions") or [{}])[0]
        us_abbr = (team.get("abbr") or "").upper()
        us = them = None
        for c in comps.get("competitors") or []:
            abbr = ((c.get("team") or {}).get("abbreviation") or "").upper()
            if abbr == us_abbr or str((c.get("team") or {}).get("id")) == str(team.get("id")):
                us = c
            else:
                them = c
        if us is None or them is None:
            return False
        live["score_us"], live["score_them"] = _score(us), _score(them)
        status = (comps.get("status") or {}).get("type") or {}
        live["detail"] = status.get("shortDetail") or status.get("detail") or live.get("detail", "")
        live["clock"] = live["detail"]
        if status.get("state") == "post":  # the game ended since the schedule was read
            live["state"] = "post"
        return True
    return False


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    wanted = teams(settings)
    if not wanted:
        raise RuntimeError("no team configured (add one under sports in config.yaml or the Settings page)")

    async def one(t: dict[str, str]) -> dict[str, Any]:
        url = BASE.format(**t)
        team_resp, sched_resp = await asyncio.gather(
            client.get(url, headers=HEADERS, timeout=20), client.get(url + "/schedule", headers=HEADERS, timeout=20)
        )
        team_resp.raise_for_status()
        sched_resp.raise_for_status()
        parsed = parse_team(team_resp.json(), sched_resp.json())
        parsed["league"] = f"{t['sport']}/{t['league']}"
        return parsed

    results = await asyncio.gather(*(one(t) for t in wanted), return_exceptions=True)
    out, errors = [], []
    for t, result in zip(wanted, results):
        if isinstance(result, BaseException):
            errors.append(f"{t['team']}: {result}")
        else:
            out.append(result)
    if not out:
        raise RuntimeError("; ".join(errors))
    # Live scores: one scoreboard call per league that has a game on right now.
    boards: dict[str, Any] = {}
    for team in out:
        if not team.get("live"):
            continue
        league = team["league"]
        if league not in boards:
            try:
                sport, lg = league.split("/", 1)
                resp = await client.get(SCOREBOARD.format(sport=sport, league=lg), params=SCOREBOARD_PARAMS.get(league), headers=HEADERS, timeout=20)
                boards[league] = resp.json() if resp.status_code == 200 else {}
            except Exception:
                boards[league] = {}
        apply_scoreboard(team, boards[league])
    return {"teams": out, "errors": errors}
