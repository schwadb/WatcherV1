"""Upcoming events from a published Outlook calendar (ICS link), with recurring events expanded."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time as dtime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from ..config import Settings


def _to_local(value: Any, tz: ZoneInfo) -> datetime:
    """Return an aware datetime in the dashboard's time zone. Naive times are assumed local."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tz)
        return value.astimezone(tz)
    return datetime.combine(value, dtime.min, tzinfo=tz)


def _text(component: Any, key: str) -> str:
    value = component.get(key)
    return str(value).strip() if value is not None else ""


def parse(ics_bytes: bytes, settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    tz = ZoneInfo(settings.timezone)
    now = (now or datetime.now(tz=tz)).astimezone(tz)
    days_ahead = int(settings.cfg["calendar"]["days_ahead"])
    window_start = datetime.combine(now.date(), dtime.min, tzinfo=tz)
    window_end = window_start + timedelta(days=days_ahead + 1)

    cal = icalendar.Calendar.from_ical(ics_bytes)
    events: list[dict[str, Any]] = []
    for ev in recurring_ical_events.of(cal, components=["VEVENT"]).between(window_start, window_end):
        if _text(ev, "STATUS").upper() == "CANCELLED":
            continue
        start_raw = ev.get("DTSTART").dt
        end_raw = ev.get("DTEND").dt if ev.get("DTEND") is not None else None
        all_day = isinstance(start_raw, date) and not isinstance(start_raw, datetime)
        start = _to_local(start_raw, tz)
        if end_raw is None:
            duration = ev.get("DURATION")
            end = start + (duration.dt if duration is not None else (timedelta(days=1) if all_day else timedelta(0)))
        else:
            end = _to_local(end_raw, tz)
        if end < now and not all_day:
            continue  # already over today
        events.append(
            {
                "title": _text(ev, "SUMMARY") or "(No title)",
                "location": _text(ev, "LOCATION"),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "all_day": all_day,
                "date": start.date().isoformat(),
                "_sort": (start, 0 if all_day else 1),
            }
        )
    events.sort(key=lambda e: e["_sort"])

    days = []
    for offset in range(days_ahead + 1):
        day = (window_start + timedelta(days=offset)).date()
        label = "Today" if offset == 0 else "Tomorrow" if offset == 1 else day.strftime("%A")
        todays = []
        for e in events:
            s = e["_sort"][0]
            e_end = datetime.fromisoformat(e["end"])
            # an event belongs to a day if it overlaps that day
            day_start = datetime.combine(day, dtime.min, tzinfo=tz)
            day_end = day_start + timedelta(days=1)
            if s < day_end and e_end > day_start and not (e["all_day"] and e_end == day_start):
                todays.append({k: v for k, v in e.items() if not k.startswith("_")})
        days.append({"date": day.isoformat(), "label": label, "events": todays})
    return {"days": days, "count": len(events)}


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    if not settings.ics_url:
        raise RuntimeError("OUTLOOK_ICS_URL is not set in .env (Outlook > Settings > Calendar > Shared calendars > Publish)")
    resp = await client.get(settings.ics_url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    if b"BEGIN:VCALENDAR" not in resp.content[:2000]:
        raise RuntimeError("the OUTLOOK_ICS_URL did not return a calendar; make sure you copied the ICS link, not the HTML one")
    return await asyncio.to_thread(parse, resp.content, settings)
