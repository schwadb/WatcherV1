"""Look up ESPN team ids for the sports tile.

Usage:  .venv/bin/python tools/find_team.py "kansas city"            # searches the common US leagues
        .venv/bin/python tools/find_team.py "nebraska" football/college-football
Prints the sport, league, id and abbreviation to put under `sports.teams` in config.yaml.
"""
from __future__ import annotations

import sys

import httpx

LEAGUES = [
    "football/nfl", "football/college-football", "basketball/nba", "basketball/wnba",
    "basketball/mens-college-basketball", "baseball/mlb", "hockey/nhl", "soccer/usa.1",
]
URL = "https://site.web.api.espn.com/apis/site/v2/sports/{league}/teams?limit=1000"


def search(query: str, leagues: list[str]) -> list[tuple[str, str, str, str]]:
    hits = []
    q = query.lower()
    with httpx.Client(headers={"User-Agent": "Mozilla/5.0 (compatible; WatcherDashboard/1.0)"}, timeout=20) as client:
        for league in leagues:
            try:
                data = client.get(URL.format(league=league)).json()
            except Exception as exc:  # noqa: BLE001
                print(f"  ({league}: {exc})")
                continue
            for sport in data.get("sports", []):
                for lg in sport.get("leagues", []):
                    for entry in lg.get("teams", []):
                        team = entry.get("team", {})
                        name = f"{team.get('displayName', '')} {team.get('location', '')} {team.get('nickname', '')}".lower()
                        if q in name or q == team.get("abbreviation", "").lower():
                            hits.append((league, team.get("id"), team.get("abbreviation"), team.get("displayName")))
    return hits


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    leagues = [sys.argv[2]] if len(sys.argv) > 2 else LEAGUES
    results = search(sys.argv[1], leagues)
    if not results:
        print("no teams found")
        sys.exit(1)
    for league, team_id, abbr, name in results:
        sport, lg = league.split("/", 1)
        print(f"{name:40} -> sport: {sport}, league: {lg}, team: {team_id}  (abbreviation {abbr})")
