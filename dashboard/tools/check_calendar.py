"""Checks that the calendar parser expands recurring events correctly, using fixtures/calendar.ics.

Run:  .venv/bin/python tools/check_calendar.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings  # noqa: E402
from app.sources.calendar import parse  # noqa: E402

settings = load_settings()
tz = ZoneInfo("America/Chicago")
# A fixed "now": Wednesday 2026-09-30 08:00 Central, so the window is Wed Sep 30 .. Wed Oct 7.
now = datetime(2026, 9, 30, 8, 0, tzinfo=tz)
result = parse((settings.fixtures_dir / "calendar.ics").read_bytes(), settings, now=now)

by_date = {d["date"]: d for d in result["days"]}
titles = lambda date: [e["title"] for e in by_date[date]["events"]]  # noqa: E731
checks = []

def check(label: str, ok: bool) -> None:
    checks.append(ok)
    print(("PASS " if ok else "FAIL ") + label)

check("window covers today + 7 days", [d["date"] for d in result["days"]] == [f"2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07"])
check("weekly stand-up appears on Mon/Wed/Fri", "Team stand-up" in titles("2026-09-30") and "Team stand-up" in titles("2026-10-05") and "Team stand-up" in titles("2026-10-07"))
check("EXDATE removes the Oct 2 stand-up", "Team stand-up" not in titles("2026-10-02"))
check("daily event appears every day", all("Lunch" in titles(d) for d in by_date))
check("all-day weekly event lands on Thursday and is flagged all_day", any(e["title"] == "Payroll due" and e["all_day"] for e in by_date["2026-10-01"]["events"]) and "Payroll due" not in titles("2026-10-02"))
check("cancelled series never appears", all("Cancelled" not in t for d in by_date for t in titles(d)))
utc_event = next((e for e in by_date["2026-10-05"]["events"] if e["title"].startswith("Evening call")), None)
check("UTC event converted to Central (23:00Z -> 6 PM CDT)", utc_event is not None and utc_event["start"].endswith("T18:00:00-05:00"))
tue = next((e for e in by_date["2026-10-06"]["events"] if e["title"].startswith("Project review")), None)
check("Windows time zone name (Central Standard Time) handled", tue is not None and tue["start"].startswith("2026-10-06T14:00:00-05:00"))
check("events sorted by time within a day (all-day first)", [e["all_day"] for e in by_date["2026-10-01"]["events"]][:1] == [True])
check("labels are Today / Tomorrow / weekday", [d["label"] for d in result["days"][:3]] == ["Today", "Tomorrow", "Friday"])

print(f"\n{sum(checks)}/{len(checks)} checks passed")
sys.exit(0 if all(checks) else 1)
