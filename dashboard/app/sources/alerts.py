"""Active severe-weather alerts from the US National Weather Service (free, no key, US only)."""
from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatch
from typing import Any

import httpx

from ..config import Settings

API = "https://api.weather.gov/alerts/active"
HEADERS = {"User-Agent": "WatcherDashboard/1.0 (github.com/schwadb/WatcherV1)", "Accept": "application/geo+json"}
SEVERITY_ORDER = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}
MAX_SHOWN = 3


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


DEFAULT_TAKEOVER_EVENTS = ["*Warning", "Tornado Watch"]


def is_takeover(event: str, patterns: list[str] | None) -> bool:
    """Does this alert deserve the full-screen takeover? Patterns use * wildcards, case-insensitive."""
    for pattern in patterns or DEFAULT_TAKEOVER_EVENTS:
        if fnmatch((event or "").lower(), str(pattern).lower()):
            return True
    return False


def parse(raw: dict[str, Any], now: datetime | None = None, takeover_events: list[str] | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    alerts: list[dict[str, Any]] = []
    for feature in raw.get("features") or []:
        p = feature.get("properties") or {}
        if p.get("messageType") == "Cancel":
            continue
        ends = _dt(p.get("ends")) or _dt(p.get("expires"))
        if ends and ends < now:
            continue
        severity = p.get("severity") or "Unknown"
        alerts.append(
            {
                "id": p.get("id") or feature.get("id"),
                "event": p.get("event") or "Weather alert",
                "severity": severity,
                "urgency": p.get("urgency"),
                "certainty": p.get("certainty"),
                "headline": p.get("headline") or "",
                "description": (p.get("description") or "")[:400],
                "instruction": (p.get("instruction") or "")[:300],
                "starts": p.get("onset") or p.get("effective"),
                "ends": ends.isoformat() if ends else None,
                "area": p.get("areaDesc") or "",
                "sender": p.get("senderName") or "",
                "takeover": is_takeover(p.get("event") or "", takeover_events),
            }
        )
    alerts.sort(key=lambda a: (0 if a["takeover"] else 1, SEVERITY_ORDER.get(a["severity"], 4), a["ends"] or ""))
    takeover = next((a for a in alerts if a["takeover"]), None)
    return {"alerts": alerts[:MAX_SHOWN], "count": len(alerts), "top": alerts[0] if alerts else None, "takeover": takeover}


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    loc = settings.cfg["location"]
    resp = await client.get(API, params={"point": f"{loc['lat']},{loc['lon']}"}, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return parse(resp.json(), takeover_events=settings.cfg["weather"].get("takeover_events"))
