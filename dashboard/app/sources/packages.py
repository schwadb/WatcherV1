"""Package tracking through 17TRACK (api.17track.net): one free key covers UPS, FedEx, USPS, Amazon and more.

Numbers live in data/packages.json (added from the phone). Registering a number with 17TRACK uses
one unit of the account's quota; asking for its status afterwards is free, so the poller asks every
30 minutes for every package that is not delivered yet.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ..config import Settings
from ..store import JsonStore

API = "https://api.17track.net/track/v2.4"
NUMBER_RE = re.compile(r"^[A-Za-z0-9]{6,40}$")
MAX_LABEL = 40
MAX_ITEMS = 20
KEEP_DELIVERED_DAYS = 2
REFRESH_MINUTES = 30

# status -> (label, sort order; higher = more urgent to look at, done)
STATUS: dict[str, tuple[str, int, bool]] = {
    "OutForDelivery": ("Out for delivery", 6, False),
    "AvailableForPickup": ("Ready for pickup", 5, False),
    "DeliveryFailure": ("Delivery attempted", 4, False),
    "Exception": ("Problem, check the carrier", 4, False),
    "InTransit": ("In transit", 3, False),
    "InfoReceived": ("Label created", 2, False),
    "NotFound": ("No tracking info yet", 1, False),
    "Expired": ("No updates for a long time", 0, False),
    "Delivered": ("Delivered", -1, True),
}


def valid_number(number: str) -> str:
    cleaned = re.sub(r"[\s-]", "", str(number or ""))
    if not NUMBER_RE.match(cleaned):
        raise ValueError("That doesn't look like a tracking number (letters and digits, 6 to 40 of them).")
    return cleaned.upper()


def store(settings: Settings) -> JsonStore:
    return JsonStore(settings.data_dir / "packages.json", {"items": []})


def parse_track(entry: dict[str, Any]) -> dict[str, Any]:
    """The parts of one 17TRACK `accepted` entry the TV shows."""
    info = entry.get("track_info") or {}
    status = str((info.get("latest_status") or {}).get("status") or "NotFound")
    label, order, done = STATUS.get(status, ("In transit", 3, False))
    event = info.get("latest_event") or {}
    providers = ((info.get("tracking") or {}).get("providers") or [])
    carrier = str(((providers[0] if providers else {}).get("provider") or {}).get("name") or "")
    eta = ((info.get("time_metrics") or {}).get("estimated_delivery_date") or {}).get("from")
    return {
        "number": str(entry.get("number") or ""),
        "status": status, "status_text": label, "order": order, "done": done,
        "carrier": carrier,
        "last_event": str(event.get("description") or ""),
        "last_time": event.get("time_iso"),
        "last_place": str(event.get("location") or ""),
        "eta": eta,
        "delivered_on": event.get("time_iso") if done else None,
    }


def eta_label(eta: Any, today: str) -> str:
    """"Arriving today" / "Arriving tomorrow" / "Arriving Fri" / "Arriving Nov 20" / ""."""
    if not eta:
        return ""
    try:
        day = datetime.fromisoformat(str(eta)).date()
        base = datetime.fromisoformat(today).date()
    except ValueError:
        return ""
    diff = (day - base).days
    if diff < 0:
        return "Expected " + day.strftime("%b %-d")
    if diff == 0:
        return "Arriving today"
    if diff == 1:
        return "Arriving tomorrow"
    if diff < 7:
        return "Arriving " + day.strftime("%a")
    return "Arriving " + day.strftime("%b %-d")


def merge(items: list[dict[str, Any]], parsed: dict[str, dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Fold fresh tracking results into the stored items and drop old delivered ones."""
    out = []
    for item in items:
        fresh = parsed.get(item.get("number"))
        if fresh:
            item = {**item, **{k: v for k, v in fresh.items() if k != "number"}, "checked": now.isoformat()}
            if item.get("done") and not item.get("delivered_seen"):
                item["delivered_seen"] = now.isoformat()
        if item.get("done"):
            seen = item.get("delivered_seen") or now.isoformat()
            try:
                if now - datetime.fromisoformat(seen) > timedelta(days=KEEP_DELIVERED_DAYS):
                    continue
            except ValueError:
                pass
        out.append(item)
    out.sort(key=lambda p: (-int(p.get("order", 3)), p.get("eta") or "9999", p.get("added") or ""))
    return out[:MAX_ITEMS]


def _headers(key: str) -> dict[str, str]:
    return {"17token": key, "Content-Type": "application/json"}


async def register(client: httpx.AsyncClient, key: str, number: str) -> dict[str, Any]:
    """Tell 17TRACK to start following a number. Returns {"ok", "carrier", "message"}."""
    resp = await client.post(f"{API}/register", headers=_headers(key), json=[{"number": number}], timeout=20)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    for item in data.get("accepted") or []:
        if str(item.get("number", "")).upper() == number.upper():
            return {"ok": True, "carrier": item.get("carrier"), "message": "Tracking started."}
    for item in data.get("rejected") or []:
        if str(item.get("number", "")).upper() == number.upper():
            err = item.get("error") or {}
            code = err.get("code")
            if code == -18019901:  # already registered on this account: fine
                return {"ok": True, "carrier": item.get("carrier"), "message": "Already being tracked."}
            return {"ok": False, "carrier": None, "message": err.get("message") or f"17TRACK refused it (code {code})."}
    return {"ok": False, "carrier": None, "message": "17TRACK gave no answer for that number."}


async def track_info(client: httpx.AsyncClient, key: str, numbers: list[str]) -> dict[str, dict[str, Any]]:
    """Latest status for up to 40 numbers per call; returns parsed entries keyed by number."""
    parsed: dict[str, dict[str, Any]] = {}
    for i in range(0, len(numbers), 40):
        chunk = numbers[i:i + 40]
        resp = await client.post(f"{API}/gettrackinfo", headers=_headers(key), json=[{"number": n} for n in chunk], timeout=30)
        resp.raise_for_status()
        for entry in (resp.json().get("data") or {}).get("accepted") or []:
            p = parse_track(entry)
            parsed[p["number"].upper()] = p
    return parsed


def parse_fixture(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["number"].upper(): p for p in (parse_track(e) for e in (raw.get("data") or {}).get("accepted") or [])}


def summary(settings: Settings, items: list[dict[str, Any]]) -> dict[str, Any]:
    today = datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
    shown = [{**p, "eta_text": eta_label(p.get("eta"), today)} for p in items]
    return {"items": shown, "configured": bool(settings.track17_key) or settings.mock, "count": len([p for p in shown if not p.get("done")])}


async def fetch(client: httpx.AsyncClient | None, settings: Settings, fixture: Path | None = None) -> dict[str, Any]:
    st = store(settings)
    now = datetime.now(timezone.utc)
    items = (st.read() or {}).get("items") or []
    active = [p["number"] for p in items if not p.get("done")]
    parsed: dict[str, dict[str, Any]] = {}
    if fixture is not None:
        fx = parse_fixture(json.loads(fixture.read_text(encoding="utf-8")))
        fake = list(fx.values())
        for i, number in enumerate(active):  # any number gets a fixture status, in order
            parsed[number.upper()] = {**fake[i % len(fake)], "number": number}
    elif active and settings.track17_key and client is not None:
        parsed = await track_info(client, settings.track17_key, active)
    if parsed or any(p.get("done") for p in items):
        merged = merge(items, parsed, now)
        if merged != items:
            st.write({"items": merged})
        items = merged
    return summary(settings, items)
