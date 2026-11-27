"""Moon phase, computed locally (no API)."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

SYNODIC_MONTH = 29.530588853  # days
REFERENCE_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
NAMES = [
    "New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
    "Full moon", "Waning gibbous", "Last quarter", "Waning crescent",
]


def moon_phase(when: datetime | None = None) -> dict[str, Any]:
    when = when or datetime.now(timezone.utc)
    days = (when - REFERENCE_NEW_MOON).total_seconds() / 86400
    phase = (days % SYNODIC_MONTH) / SYNODIC_MONTH  # 0 = new, 0.5 = full
    index = int(phase * 8 + 0.5) % 8
    illumination = round((1 - math.cos(2 * math.pi * phase)) / 2 * 100)
    to_full = ((0.5 - phase) % 1) * SYNODIC_MONTH
    to_new = ((1.0 - phase) % 1) * SYNODIC_MONTH
    return {"phase": round(phase, 3), "name": NAMES[index], "index": index, "illumination": illumination,
            "next_full_days": round(to_full, 1), "next_new_days": round(to_new, 1)}
