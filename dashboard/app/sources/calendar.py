"""Upcoming events from one or more published calendars (ICS links), with recurring events expanded."""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, time as dtime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from ..cache import describe
from ..config import Settings

PALETTE = ["#5aa9ff", "#f5b942", "#3ecf8e", "#ff6b6b", "#b06cff", "#4dd0e1"]
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def calendars(settings: Settings) -> list[dict[str, Any]]:
    """The configured calendars: [{name, url, color}]. Falls back to OUTLOOK_ICS_URL as a single 'Work' calendar."""
    raw = settings.cfg.get("calendars") or []
    unexpanded = getattr(settings, "raw_cfg", {}).get("calendars") or []
    out: list[dict[str, Any]] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        color = str(entry.get("color") or "")
        template = str((unexpanded[i] if i < len(unexpanded) and isinstance(unexpanded[i], dict) else {}).get("url") or "")
        env_match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", template.strip())
        out.append(
            {
                "name": str(entry.get("name") or f"Calendar {i + 1}"),
                "url": str(entry.get("url") or "").strip(),
                "color": color if _COLOR.match(color) else PALETTE[i % len(PALETTE)],
                "env": env_match.group(1) if env_match else "",
            }
        )
    if not out and settings.ics_url:
        out = [{"name": "Work", "url": settings.ics_url, "color": PALETTE[0]}]
    return out


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


def _window(settings: Settings, now: datetime | None) -> tuple[ZoneInfo, datetime, datetime, datetime]:
    tz = ZoneInfo(settings.timezone)
    now = (now or datetime.now(tz=tz)).astimezone(tz)
    days_ahead = int(settings.cfg["calendar"]["days_ahead"])
    start = datetime.combine(now.date(), dtime.min, tzinfo=tz)
    return tz, now, start, start + timedelta(days=days_ahead + 1)


def events_from_ics(
    ics_bytes: bytes, settings: Settings, now: datetime | None = None, calendar: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    tz, now, window_start, window_end = _window(settings, now)
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
                "calendar": (calendar or {}).get("name", ""),
                "color": (calendar or {}).get("color", PALETTE[0]),
                "_sort": (start, 0 if all_day else 1),
            }
        )
    return events


def group_by_day(events: list[dict[str, Any]], settings: Settings, now: datetime | None = None) -> list[dict[str, Any]]:
    tz, now, window_start, _ = _window(settings, now)
    days_ahead = int(settings.cfg["calendar"]["days_ahead"])
    events = sorted(events, key=lambda e: e["_sort"])
    days = []
    for offset in range(days_ahead + 1):
        day = (window_start + timedelta(days=offset)).date()
        label = "Today" if offset == 0 else "Tomorrow" if offset == 1 else day.strftime("%A")
        day_start = datetime.combine(day, dtime.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        todays = []
        for e in events:
            s = e["_sort"][0]
            e_end = datetime.fromisoformat(e["end"])
            # an event belongs to a day if it overlaps that day
            if s < day_end and e_end > day_start and not (e["all_day"] and e_end == day_start):
                todays.append({k: v for k, v in e.items() if not k.startswith("_")})
        days.append({"date": day.isoformat(), "label": label, "events": todays})
    return days


def parse(ics_bytes: bytes, settings: Settings, now: datetime | None = None, calendar: dict[str, Any] | None = None) -> dict[str, Any]:
    """One ICS file -> {days, count}. Kept for tools/check_calendar.py and mock mode."""
    events = events_from_ics(ics_bytes, settings, now, calendar)
    return {"days": group_by_day(events, settings, now), "count": len(events)}


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    wanted = calendars(settings)
    if not wanted:
        raise RuntimeError("OUTLOOK_ICS_URL is not set in .env (Outlook > Settings > Calendar > Shared calendars > Publish)")

    async def one(cal: dict[str, Any]) -> list[dict[str, Any]]:
        if not cal["url"]:
            raise RuntimeError(f"link not set ({cal['env']} in .env)" if cal.get("env") else "link not set")
        resp = await client.get(cal["url"], timeout=30, follow_redirects=True)
        resp.raise_for_status()
        if b"BEGIN:VCALENDAR" not in resp.content[:2000]:
            raise RuntimeError("the link did not return a calendar; copy the ICS link, not the HTML one")
        return await asyncio.to_thread(events_from_ics, resp.content, settings, None, cal)

    results = await asyncio.gather(*(one(c) for c in wanted), return_exceptions=True)
    events: list[dict[str, Any]] = []
    meta, errors = [], []
    for cal, result in zip(wanted, results):
        if isinstance(result, BaseException):
            errors.append(f"{cal['name']}: {describe(result)}")
            meta.append({"name": cal["name"], "color": cal["color"], "ok": False, "error": str(result)})
        else:
            events.extend(result)
            meta.append({"name": cal["name"], "color": cal["color"], "ok": True, "error": None})
    if not any(m["ok"] for m in meta):
        raise RuntimeError("; ".join(errors))
    return {"days": group_by_day(events, settings), "count": len(events), "calendars": meta, "errors": errors}
