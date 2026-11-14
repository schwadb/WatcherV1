"""Family messages: short notes posted from the phone that show on the TV for a while.

Pure helpers live here (tested in tools/check_parsers.py); the routes are in app/manage.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

TTL_CHOICES = ("midnight", "1h", "4h", "never")
MAX_TEXT = 200
MAX_FROM = 30
MAX_ITEMS = 12


def expiry_for(ttl: str, now: datetime) -> str | None:
    """When a message posted at `now` (timezone-aware, dashboard zone) disappears, as ISO text; None = never."""
    ttl = (ttl or "midnight").lower()
    if ttl == "never":
        return None
    if ttl == "1h":
        return (now + timedelta(hours=1)).isoformat()
    if ttl == "4h":
        return (now + timedelta(hours=4)).isoformat()
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.isoformat()


def make(text: str, sender: str, ttl: str, now: datetime) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:8],
        "text": " ".join(str(text).split())[:MAX_TEXT],
        "from": " ".join(str(sender).split())[:MAX_FROM],
        "created": now.isoformat(),
        "expires": expiry_for(ttl, now),
        "ttl": ttl if ttl in TTL_CHOICES else "midnight",
    }


def prune(items: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Drop expired messages; keep the newest MAX_ITEMS."""
    keep = []
    for m in items:
        exp = m.get("expires")
        if exp:
            try:
                if datetime.fromisoformat(exp) <= now:
                    continue
            except ValueError:
                continue
        keep.append(m)
    keep.sort(key=lambda m: m.get("created") or "", reverse=True)
    return keep[:MAX_ITEMS]
