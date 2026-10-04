"""Management API: photo uploads, to-do list, notes, settings, secrets and system actions.

Everything here is used by static/manage.html (the phone / on-TV settings page).
Mutating routes require the PIN when DASHBOARD_PIN is set in .env.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

import httpx
from dotenv import set_key, unset_key
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from PIL import Image
from ruamel.yaml import YAML

from .cache import refresh_once
from .config import DEFAULTS, ROOT, Settings
from .screen import close_dashboard, dashboard_window_running, launch_dashboard, run_screen, set_autostart
from .sources import photos as photos_src
from .sources import spotify as spotify_src
from .store import JsonStore

try:  # iPhone HEIC photos, when the optional package is present
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except Exception:  # noqa: BLE001
    HEIC_SUPPORTED = False

log = logging.getLogger("dashboard")
router = APIRouter()
STATIC_DIR = ROOT / "static"
SECRET_KEYS = ("FINNHUB_API_KEY", "OUTLOOK_ICS_URL", "FAMILY_ICS_URL", "DASHBOARD_PIN", "SPOTIFY_CLIENT_ID")
UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
_HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_SYMBOL = re.compile(r"^[A-Z0-9.\-]{1,10}$")
_LEAGUE = re.compile(r"^[a-z0-9.\-]+$")

STATE_TZ = {
    "CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York", "GA": "America/New_York",
    "ME": "America/New_York", "MD": "America/New_York", "MA": "America/New_York", "NH": "America/New_York",
    "NJ": "America/New_York", "NY": "America/New_York", "NC": "America/New_York", "OH": "America/New_York",
    "PA": "America/New_York", "RI": "America/New_York", "SC": "America/New_York", "VT": "America/New_York",
    "VA": "America/New_York", "WV": "America/New_York", "DC": "America/New_York", "MI": "America/Detroit",
    "IN": "America/Indiana/Indianapolis", "KY": "America/New_York", "TN": "America/Chicago",
    "AL": "America/Chicago", "AR": "America/Chicago", "IL": "America/Chicago", "IA": "America/Chicago",
    "KS": "America/Chicago", "LA": "America/Chicago", "MN": "America/Chicago", "MS": "America/Chicago",
    "MO": "America/Chicago", "NE": "America/Chicago", "ND": "America/Chicago", "OK": "America/Chicago",
    "SD": "America/Chicago", "TX": "America/Chicago", "WI": "America/Chicago",
    "AZ": "America/Phoenix", "CO": "America/Denver", "ID": "America/Boise", "MT": "America/Denver",
    "NM": "America/Denver", "UT": "America/Denver", "WY": "America/Denver",
    "CA": "America/Los_Angeles", "NV": "America/Los_Angeles", "OR": "America/Los_Angeles", "WA": "America/Los_Angeles",
    "AK": "America/Anchorage", "HI": "Pacific/Honolulu",
}


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def _settings(request: Request) -> Settings:
    return request.app.state.settings


def require_pin(request: Request) -> None:
    pin = _settings(request).pin
    if not pin:
        return
    given = request.headers.get("X-Pin") or request.cookies.get("dashboard_pin") or ""
    if not secrets.compare_digest(given, pin):
        raise HTTPException(401, "PIN required")


def _store(request: Request, name: str, default: Any) -> JsonStore:
    stores = getattr(request.app.state, "stores", None)
    if stores is None:
        stores = request.app.state.stores = {}
    if name not in stores:
        stores[name] = JsonStore(_settings(request).data_dir / f"{name}.json", default)
    return stores[name]


def _envelope(name: str, data: Any) -> dict[str, Any]:
    return {"ok": True, "source": name, "fetched_at": datetime.now(timezone.utc).isoformat(), "age_seconds": 0, "stale": False, "error": None, "data": data}


def _today(settings: Settings) -> str:
    return datetime.now(ZoneInfo(settings.timezone)).date().isoformat()


# ---------------------------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------------------------
@router.get("/manage")
async def manage_page():
    return FileResponse(STATIC_DIR / "manage.html", headers={"Cache-Control": "no-cache"})


@router.get("/upload")
async def upload_redirect():
    return RedirectResponse("/manage#photos", status_code=307)


@router.get("/lists")
async def lists_redirect():
    return RedirectResponse("/manage#todo", status_code=307)


@router.post("/api/pin")
async def api_pin(request: Request):
    body = await request.json()
    pin = _settings(request).pin
    if pin and not secrets.compare_digest(str(body.get("pin", "")), pin):
        raise HTTPException(401, "wrong PIN")
    resp = JSONResponse({"ok": True})
    if pin:
        resp.set_cookie("dashboard_pin", pin, max_age=30 * 86400, httponly=True, samesite="lax")
    return resp


# ---------------------------------------------------------------------------------------------
# photos
# ---------------------------------------------------------------------------------------------
def _safe_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[:60].strip("._") or "photo"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}-{base}"


@router.get("/api/photos/list")
async def photos_list(request: Request):
    settings = _settings(request)
    folder = settings.photo_dir
    out = []
    if folder.exists():
        for path in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_file() or path.suffix.lower() not in photos_src.EXTENSIONS or path.name.startswith("."):
                continue
            pid = photos_src.photo_id(path, folder)
            thumb = settings.cache_dir / f"{pid}.jpg"
            stat = path.stat()
            out.append({"name": path.name, "size": stat.st_size, "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(), "thumb": f"/photos/{pid}.jpg" if thumb.exists() else None})
    return {"photos": out, "folder": str(folder), "heic_supported": HEIC_SUPPORTED}


@router.post("/api/photos/upload")
async def photos_upload(request: Request, files: list[UploadFile]):
    require_pin(request)
    settings = _settings(request)
    folder = settings.photo_dir
    folder.mkdir(parents=True, exist_ok=True)
    max_bytes = int(float(settings.cfg["photos"].get("max_upload_mb", 25)) * 1024 * 1024)
    saved, rejected = [], []
    for up in files:
        name = up.filename or "photo"
        ext = Path(name).suffix.lower()
        if ext not in UPLOAD_EXTENSIONS:
            rejected.append({"name": name, "reason": "Only JPG, PNG, WEBP or HEIC photos are supported."})
            continue
        data = await up.read()
        if len(data) > max_bytes:
            rejected.append({"name": name, "reason": f"Larger than {max_bytes // (1024 * 1024)} MB."})
            continue
        if ext in (".heic", ".heif") and not HEIC_SUPPORTED:
            rejected.append({"name": name, "reason": "iPhone HEIC photos aren't supported on this Pi. Export it as JPEG, or set the iPhone camera to 'Most Compatible'."})
            continue
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
        except Exception:  # noqa: BLE001
            rejected.append({"name": name, "reason": "That file isn't a readable photo."})
            continue
        try:
            if ext in (".heic", ".heif"):
                target = folder / (Path(_safe_name(name)).stem + ".jpg")
                with Image.open(io.BytesIO(data)) as im:
                    from PIL import ImageOps

                    im = ImageOps.exif_transpose(im) or im
                    im.convert("RGB").save(target, "JPEG", quality=92)
            else:
                target = folder / _safe_name(name)
                target.write_bytes(data)
            saved.append(target.name)
        except Exception as exc:  # noqa: BLE001
            rejected.append({"name": name, "reason": f"Could not save: {exc}"})
    if saved and "photos" in request.app.state.sources:
        cache, fetch = request.app.state.sources["photos"]
        await refresh_once(cache, fetch)
    return {"saved": saved, "rejected": rejected}


@router.delete("/api/photos/{name}")
async def photos_delete(request: Request, name: str):
    require_pin(request)
    settings = _settings(request)
    folder = settings.photo_dir.resolve()
    path = (folder / Path(name).name).resolve()
    if path.parent != folder or not path.is_file():
        raise HTTPException(404, "photo not found")
    pid = photos_src.photo_id(path, settings.photo_dir)
    path.unlink()
    (settings.cache_dir / f"{pid}.jpg").unlink(missing_ok=True)
    if "photos" in request.app.state.sources:
        cache, fetch = request.app.state.sources["photos"]
        await refresh_once(cache, fetch)
    return {"ok": True}


# ---------------------------------------------------------------------------------------------
# to-do list and notes
# ---------------------------------------------------------------------------------------------
def _prune_done(items: list[dict[str, Any]], today: str) -> list[dict[str, Any]]:
    """Checked items disappear the day after they were checked."""
    return [i for i in items if not (i.get("done") and (i.get("done_on") or "") < today)]


@router.get("/api/todo")
async def todo_get(request: Request):
    store = _store(request, "todo", {"items": []})
    today = _today(_settings(request))
    data = store.read()
    pruned = _prune_done(data.get("items", []), today)
    if len(pruned) != len(data.get("items", [])):
        data = await store.update(lambda d: {**d, "items": _prune_done(d.get("items", []), today)})
    items = sorted(data["items"], key=lambda i: (bool(i.get("done")), i.get("created", "")))
    return _envelope("todo", {"items": items, "max_items": int(_settings(request).cfg.get("todo", {}).get("max_items", 8))})


@router.post("/api/todo")
async def todo_add(request: Request):
    require_pin(request)
    body = await request.json()
    text = str(body.get("text", "")).strip()[:200]
    if not text:
        raise HTTPException(422, "text is required")
    item = {"id": uuid.uuid4().hex[:8], "text": text, "done": False, "created": datetime.now(timezone.utc).isoformat(), "done_on": None}
    await _store(request, "todo", {"items": []}).update(lambda d: {**d, "items": d.get("items", []) + [item]})
    return item


@router.patch("/api/todo/{item_id}")
async def todo_patch(request: Request, item_id: str):
    require_pin(request)
    body = await request.json()
    today = _today(_settings(request))

    def apply(d):
        for i in d.get("items", []):
            if i["id"] == item_id:
                if "done" in body:
                    i["done"] = bool(body["done"])
                    i["done_on"] = today if i["done"] else None
                if "text" in body and str(body["text"]).strip():
                    i["text"] = str(body["text"]).strip()[:200]
        return d

    data = await _store(request, "todo", {"items": []}).update(apply)
    item = next((i for i in data["items"] if i["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "item not found")
    return item


@router.delete("/api/todo/{item_id}")
async def todo_delete(request: Request, item_id: str):
    require_pin(request)
    await _store(request, "todo", {"items": []}).update(lambda d: {**d, "items": [i for i in d.get("items", []) if i["id"] != item_id]})
    return {"ok": True}


@router.delete("/api/todo")
async def todo_clear_done(request: Request):
    require_pin(request)
    await _store(request, "todo", {"items": []}).update(lambda d: {**d, "items": [i for i in d.get("items", []) if not i.get("done")]})
    return {"ok": True}


@router.get("/api/notes")
async def notes_get(request: Request):
    return _envelope("notes", _store(request, "notes", {"text": "", "updated": None}).read())


@router.put("/api/notes")
async def notes_put(request: Request):
    require_pin(request)
    body = await request.json()
    text = str(body.get("text", ""))[:2000]
    data = await _store(request, "notes", {"text": "", "updated": None}).update(lambda d: {"text": text, "updated": datetime.now(timezone.utc).isoformat()})
    return data


# ---------------------------------------------------------------------------------------------
# settings and secrets
# ---------------------------------------------------------------------------------------------
def _mask(value: str) -> dict[str, Any]:
    value = value or ""
    if not value:
        return {"set": False, "hint": ""}
    hint = value if len(value) <= 6 else f"{value[:3]}…{value[-3:]}"
    if value.startswith("http"):
        hint = value[:28] + "…"
    return {"set": True, "hint": hint}


def editable_config(settings: Settings) -> dict[str, Any]:
    """The whitelisted part of the config the settings page may read and write."""
    c = settings.raw_cfg or settings.cfg
    symbols = c["stocks"]["symbols"]
    if isinstance(symbols, list):
        symbols = {s: s for s in symbols}
    sports_cfg = c.get("sports") if isinstance(c.get("sports"), dict) else {"refresh_minutes": 10, "teams": c.get("sports") or []}
    return {
        "location": {k: c["location"].get(k) for k in ("name", "lat", "lon", "timezone")},
        "units": c.get("units", "imperial"),
        "clock_24h": bool(c.get("clock_24h", False)),
        "panels": {**DEFAULTS["panels"], **(c.get("panels") or {})},
        "weather": {k: c["weather"].get(k, DEFAULTS["weather"][k]) for k in ("forecast_days", "hourly_hours", "air_quality", "alerts", "takeover", "takeover_minutes", "takeover_sound")},
        "chronalert": {**DEFAULTS["chronalert"], **(c.get("chronalert") or {})},
        "radar": {k: c["radar"].get(k, DEFAULTS["radar"][k]) for k in ("provider", "zoom")},
        "stocks": {"symbols": symbols},
        "calendars": [{"name": x.get("name", ""), "url": x.get("url", ""), "color": x.get("color", "")} for x in (c.get("calendars") or []) if isinstance(x, dict)],
        "calendar": {k: c["calendar"].get(k, DEFAULTS["calendar"][k]) for k in ("days_ahead", "max_events")},
        "countdowns": [{"title": x.get("title", ""), "date": str(x.get("date", "")), "icon": x.get("icon", "")} for x in (c.get("countdowns") or []) if isinstance(x, dict)],
        "sports": {"teams": [{"sport": t.get("sport", ""), "league": t.get("league", ""), "team": str(t.get("team", t.get("team_id", ""))), "name": t.get("name", "")} for t in (sports_cfg.get("teams") or []) if isinstance(t, dict)]},
        "news": {"feeds": [{"name": f.get("name", ""), "url": f.get("url", "")} for f in (c["news"].get("feeds") or []) if isinstance(f, dict)]},
        "photos": {k: c["photos"].get(k, DEFAULTS["photos"][k]) for k in ("seconds_per_photo", "order", "max_upload_mb")},
        "todo": {"max_items": (c.get("todo") or {}).get("max_items", 8)},
        "now_playing": {"provider": (c.get("now_playing") or {}).get("provider", "off")},
        "display": {k: c["display"].get(k, DEFAULTS["display"][k]) for k in ("reload_at", "screen_off", "screen_on", "dim_from", "dim_level", "control", "start_at_login", "locked_kiosk", "stop_idle_lock")},
    }


def validate_config(body: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Check an edited config; returns (clean subset, errors). Only known keys survive."""
    errors: list[str] = []
    clean: dict[str, Any] = {}

    def num(section: str, key: str, lo: float, hi: float, cast=float):
        try:
            v = cast(body[section][key])
        except (KeyError, TypeError, ValueError):
            return None
        if not lo <= v <= hi:
            errors.append(f"{section}.{key} must be between {lo} and {hi}")
            return None
        return v

    if "location" in body:
        loc = body["location"] or {}
        lat, lon = num("location", "lat", -90, 90), num("location", "lon", -180, 180)
        tzname = str(loc.get("timezone", "")).strip()
        if tzname and tzname not in available_timezones():
            errors.append("location.timezone is not a known time zone")
        clean["location"] = {"name": str(loc.get("name", "")).strip()[:60] or "Home", "lat": lat, "lon": lon, "timezone": tzname or "America/Chicago"}
        if lat is None or lon is None:
            errors.append("location needs a latitude and longitude (use the ZIP lookup)")
    if "units" in body:
        clean["units"] = "metric" if str(body["units"]).lower() == "metric" else "imperial"
    if "clock_24h" in body:
        clean["clock_24h"] = bool(body["clock_24h"])
    if "panels" in body:
        clean["panels"] = {k: bool((body["panels"] or {}).get(k, True)) for k in DEFAULTS["panels"]}
    if "weather" in body:
        w = body["weather"] or {}
        clean["weather"] = {
            "forecast_days": int(num("weather", "forecast_days", 1, 7, int) or 5),
            "hourly_hours": int(num("weather", "hourly_hours", 4, 12, int) or 8),
            "air_quality": bool(w.get("air_quality", True)),
            "alerts": bool(w.get("alerts", True)),
            "takeover": bool(w.get("takeover", True)),
            "takeover_minutes": int(num("weather", "takeover_minutes", 1, 60, int) or 10),
            "takeover_sound": bool(w.get("takeover_sound", True)),
        }
    if "chronalert" in body:
        ca = body["chronalert"] or {}
        mode = str(ca.get("mode", "off")).lower()
        url = str(ca.get("url", "")).strip()
        if url and not url.startswith(("http://", "https://")):
            errors.append("chronalert.url must start with http://")
        clean["chronalert"] = {
            "mode": mode if mode in ("off", "rotate", "button") else "off",
            "url": url,
            "show_seconds": int(num("chronalert", "show_seconds", 10, 3600, int) or 90),
            "photo_seconds": int(num("chronalert", "photo_seconds", 10, 3600, int) or 180),
            "open_mode": "window" if str(ca.get("open_mode", "iframe")).lower() == "window" else "iframe",
        }
    if "radar" in body:
        provider = str((body["radar"] or {}).get("provider", "rainviewer")).lower()
        if provider not in ("rainviewer", "mesonet"):
            errors.append("radar.provider must be rainviewer or mesonet")
        clean["radar"] = {"provider": provider, "zoom": int(num("radar", "zoom", 4, 9, int) or 6)}
    if "stocks" in body:
        symbols = {}
        for sym, name in ((body["stocks"] or {}).get("symbols") or {}).items():
            sym = str(sym).upper().strip()
            if not _SYMBOL.match(sym):
                errors.append(f"stock symbol '{sym}' looks wrong")
                continue
            symbols[sym] = str(name or sym).strip()[:30] or sym
        clean["stocks"] = {"symbols": symbols}
    if "calendars" in body:
        cals = []
        for i, cal in enumerate(body["calendars"] or []):
            url = str((cal or {}).get("url", "")).strip()
            color = str((cal or {}).get("color", "")).strip()
            if url and not (url.startswith(("http://", "https://", "webcal://")) or re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", url)):
                errors.append(f"calendar {i + 1}: the link must start with https:// (or be ${{NAME}} from .env)")
            if color and not _COLOR.match(color):
                errors.append(f"calendar {i + 1}: color must look like #5aa9ff")
            if url:
                cals.append({"name": str((cal or {}).get("name", "")).strip()[:30] or f"Calendar {i + 1}", "url": url.replace("webcal://", "https://"), "color": color})
        clean["calendars"] = cals
    if "calendar" in body:
        clean["calendar"] = {"days_ahead": int(num("calendar", "days_ahead", 1, 14, int) or 7), "max_events": int(num("calendar", "max_events", 3, 20, int) or 9)}
    if "countdowns" in body:
        cds = []
        for i, cd in enumerate(body["countdowns"] or []):
            date_s = str((cd or {}).get("date", "")).strip()
            title = str((cd or {}).get("title", "")).strip()[:40]
            if not title and not date_s:
                continue
            try:
                datetime.strptime(date_s, "%Y-%m-%d")
            except ValueError:
                errors.append(f"countdown '{title or i + 1}': date must be YYYY-MM-DD")
                continue
            cds.append({"title": title or "Countdown", "date": date_s, "icon": str((cd or {}).get("icon", "")).strip()[:4]})
        clean["countdowns"] = cds
    if "sports" in body:
        teams = []
        for t in (body["sports"] or {}).get("teams") or []:
            sport, league, team = (str((t or {}).get(k, "")).strip().lower() for k in ("sport", "league", "team"))
            if not (sport and league and team):
                continue
            if not (_LEAGUE.match(sport) and _LEAGUE.match(league) and re.fullmatch(r"[a-z0-9]{1,8}", team)):
                errors.append(f"team entry '{team}' looks wrong (use the search box)")
                continue
            teams.append({"sport": sport, "league": league, "team": team.upper() if team.isalpha() else team, "name": str((t or {}).get("name", "")).strip()[:40]})
        clean["sports"] = {"teams": teams}
    if "news" in body:
        feeds = []
        for i, f in enumerate((body["news"] or {}).get("feeds") or []):
            url = str((f or {}).get("url", "")).strip()
            if not url:
                continue
            if not url.startswith(("http://", "https://")):
                errors.append(f"news feed {i + 1}: the address must start with https://")
                continue
            feeds.append({"name": str((f or {}).get("name", "")).strip()[:20] or f"Feed {i + 1}", "url": url})
        clean["news"] = {"feeds": feeds}
    if "photos" in body:
        order = str((body["photos"] or {}).get("order", "shuffle")).lower()
        clean["photos"] = {"seconds_per_photo": int(num("photos", "seconds_per_photo", 5, 600, int) or 20), "order": order if order in ("shuffle", "name") else "shuffle", "max_upload_mb": int(num("photos", "max_upload_mb", 1, 100, int) or 25)}
    if "todo" in body:
        clean["todo"] = {"max_items": int(num("todo", "max_items", 1, 20, int) or 8)}
    if "now_playing" in body:
        provider = str((body["now_playing"] or {}).get("provider", "off")).lower()
        clean["now_playing"] = {"provider": provider if provider in ("off", "spotify") else "off"}
    if "display" in body:
        d = body["display"] or {}
        out = {}
        for key in ("reload_at", "screen_off", "screen_on", "dim_from"):
            v = str(d.get(key, "")).strip()
            if v and not _HHMM.match(v):
                errors.append(f"display.{key} must be a time like 22:30")
            out[key] = v
        if not out["reload_at"]:
            out["reload_at"] = "03:30"
        out["dim_level"] = num("display", "dim_level", 0, 0.9) if d.get("dim_level") not in (None, "") else 0.5
        out["control"] = "off" if str(d.get("control", "auto")).lower() == "off" else "auto"
        out["start_at_login"] = bool(d.get("start_at_login", True))
        out["locked_kiosk"] = bool(d.get("locked_kiosk", False))
        out["stop_idle_lock"] = bool(d.get("stop_idle_lock", True))
        clean["display"] = out
    return clean, errors


def write_config(path: Path, clean: dict[str, Any]) -> None:
    """Merge the edited keys into config.yaml, keeping the file's comments."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    source = path if path.exists() else ROOT / "config.example.yaml"
    doc = yaml.load(source.read_text(encoding="utf-8")) if source.exists() else {}
    if doc is None:
        doc = {}
    for section, value in clean.items():
        if isinstance(value, dict) and isinstance(doc.get(section), dict) and section not in ("panels",):
            for key, v in value.items():
                doc[section][key] = v
        else:
            doc[section] = value
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.dump(doc, fh)
    os.replace(tmp, path)


@router.get("/api/settings")
async def settings_get(request: Request):
    require_pin(request)
    settings = _settings(request)
    env = {k: _mask(os.environ.get(k, "")) for k in SECRET_KEYS}
    return {
        "config": editable_config(settings),
        "secrets": env,
        "config_path": str(settings.config_path),
        "config_version": settings.version,
        "timezones": sorted(t for t in available_timezones() if t.startswith(("America/", "Pacific/Honolulu", "Europe/", "Australia/", "Asia/"))),
        "warnings": settings.errors,
    }


@router.put("/api/settings")
async def settings_put(request: Request):
    require_pin(request)
    settings = _settings(request)
    body = await request.json()
    clean, errors = validate_config(body.get("config") or {})
    secrets_in = body.get("secrets") or {}
    env_path = ROOT / ".env"
    for key, value in secrets_in.items():
        if key not in SECRET_KEYS:
            errors.append(f"unknown secret {key}")
            continue
        value = str(value or "")
        if value and "\n" in value:
            errors.append(f"{key} must be a single line")
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=422)
    if clean:
        await asyncio.to_thread(write_config, settings.config_path, clean)
    autostart_note = None
    if "display" in clean:
        autostart_note = await asyncio.to_thread(set_autostart, clean["display"]["start_at_login"], int(settings.cfg["server"]["port"]))
    changed_secrets = []
    for key, value in secrets_in.items():
        value = str(value or "")
        if not value:
            continue  # blank = unchanged
        if not env_path.exists():
            env_path.write_text("", encoding="utf-8")
        if value == "__clear__":
            unset_key(str(env_path), key)
            os.environ.pop(key, None)
        else:
            set_key(str(env_path), key, value.strip(), quote_mode="never")
            os.environ[key] = value.strip()
        changed_secrets.append(key)
    from .main import reload_sources  # late import: main imports this module

    new_settings = await reload_sources(request.app)
    return {"ok": True, "config_version": new_settings.version, "changed_secrets": changed_secrets, "warnings": new_settings.errors, "autostart": autostart_note}


@router.get("/api/zip/{zipcode}")
async def zip_lookup(request: Request, zipcode: str):
    if not re.fullmatch(r"\d{5}", zipcode):
        raise HTTPException(422, "enter a 5-digit US ZIP code")
    client: httpx.AsyncClient = request.app.state.client
    resp = await client.get(f"https://api.zippopotam.us/us/{zipcode}", timeout=15)
    if resp.status_code == 404:
        raise HTTPException(404, "ZIP code not found")
    resp.raise_for_status()
    place = resp.json()["places"][0]
    state = place.get("state abbreviation", "")
    return {
        "name": f"{place['place name']}, {state}",
        "lat": round(float(place["latitude"]), 4),
        "lon": round(float(place["longitude"]), 4),
        "timezone": STATE_TZ.get(state, "America/Chicago"),
    }


_chron_status: dict[str, Any] = {"checked": 0.0, "reachable": False, "url": ""}


@router.get("/api/chronalert/status")
async def chronalert_status(request: Request):
    """Is the ChronAlert app answering? The dashboard only rotates to its map when it is."""
    settings = request.app.state.settings
    url = (settings.cfg.get("chronalert") or {}).get("url") or "http://127.0.0.1:8420/"
    now = time.monotonic()
    if _chron_status["url"] == url and now - _chron_status["checked"] < 60:
        return {"reachable": _chron_status["reachable"], "url": url, "cached": True}
    reachable = False
    try:
        async with httpx.AsyncClient(timeout=4, follow_redirects=True, verify=False) as client:  # LAN app, often plain http
            resp = await client.get(url)
            reachable = resp.status_code < 500
    except Exception:
        reachable = False
    _chron_status.update(checked=now, reachable=reachable, url=url)
    return {"reachable": reachable, "url": url, "cached": False}


@router.get("/api/sports/search")
async def sports_search(request: Request, q: str = ""):
    from .sources.sports import HEADERS

    q = q.strip().lower()
    if len(q) < 2:
        return {"teams": []}
    leagues = ["football/nfl", "football/college-football", "basketball/nba", "basketball/wnba", "basketball/mens-college-basketball", "baseball/mlb", "hockey/nhl", "soccer/usa.1"]
    client: httpx.AsyncClient = request.app.state.client

    async def one(league: str):
        try:
            resp = await client.get(f"https://site.web.api.espn.com/apis/site/v2/sports/{league}/teams?limit=1000", headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("team search %s failed: %s", league, exc)
            return []
        hits = []
        for sport in data.get("sports", []):
            for lg in sport.get("leagues", []):
                for entry in lg.get("teams", []):
                    team = entry.get("team", {})
                    hay = f"{team.get('displayName', '')} {team.get('location', '')} {team.get('nickname', '')} {team.get('abbreviation', '')}".lower()
                    if q in hay:
                        sport_name, league_name = league.split("/", 1)
                        hits.append({"sport": sport_name, "league": league_name, "team": str(team.get("id")), "abbr": team.get("abbreviation"), "name": team.get("displayName"), "logo": (team.get("logos") or [{}])[0].get("href")})
        return hits

    results = await asyncio.gather(*(one(lg) for lg in leagues))
    teams = [t for group in results for t in group][:30]
    return {"teams": teams}


# ---------------------------------------------------------------------------------------------
# system
# ---------------------------------------------------------------------------------------------
def _run(cmd: list[str], timeout: int = 240) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return 127, f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def _git_version() -> str:
    code, out = _run(["git", "rev-parse", "--short", "HEAD"], timeout=10)
    return out if code == 0 else "unknown"


def _lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def _machine() -> dict[str, str]:
    """A human name for this computer and which kind of system it is."""
    model = ""
    for path in ("/proc/device-tree/model", "/sys/devices/virtual/dmi/id/product_name"):
        try:
            model = Path(path).read_text(errors="replace").strip("\x00\n ")
            if model:
                break
        except OSError:
            continue
    if "raspberry pi" in model.lower():
        platform = "Raspberry Pi OS"
    elif Path("/etc/arch-release").exists():
        platform = "Omarchy / Arch Linux" if (Path.home() / ".config" / "hypr").exists() else "Arch Linux"
    elif Path("/etc/debian_version").exists():
        platform = "Debian / Ubuntu"
    else:
        platform = "Linux"
    if model.startswith("MacPro6"):
        model = "Mac Pro (2013)"
    return {"machine": model or "Linux PC", "platform": platform}


def _cpu_temp() -> float | None:
    try:
        return round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
    except (OSError, ValueError):
        return None


@router.get("/api/system")
async def system_get(request: Request):
    settings = _settings(request)
    usage = shutil.disk_usage(ROOT)
    return {
        "version": await asyncio.to_thread(_git_version),
        "hostname": socket.gethostname(),
        "ip": _lan_ip(),
        "port": settings.cfg["server"]["port"],
        "uptime_seconds": round(time.time() - request.app.state.started),
        "disk_free_gb": round(usage.free / 1e9, 1),
        "cpu_temp_c": _cpu_temp(),
        "mock": settings.mock,
        "config_path": str(settings.config_path),
        "config_version": settings.version,
        "secrets_set": {k: bool(os.environ.get(k)) for k in SECRET_KEYS},
        "setup_needed": settings.setup_needed(),
        "heic_supported": HEIC_SUPPORTED,
        "python": sys.version.split()[0],
        **_machine(),
    }


def _exit_soon() -> None:
    time.sleep(0.5)
    os._exit(0)  # systemd (Restart=always) starts us again


@router.post("/api/system/restart")
async def system_restart(request: Request, background: BackgroundTasks):
    require_pin(request)
    background.add_task(_exit_soon)
    return {"ok": True, "message": "Restarting the dashboard service. The screen comes back in about 10 seconds."}


@router.post("/api/system/update")
async def system_update(request: Request, background: BackgroundTasks):
    require_pin(request)
    code, pull = await asyncio.to_thread(_run, ["git", "pull", "--ff-only"])
    log_lines = [f"$ git pull --ff-only\n{pull}"]
    if code != 0:
        return JSONResponse({"ok": False, "log": "\n".join(log_lines), "message": "Update failed; nothing was changed."}, status_code=500)
    pip = str(ROOT / ".venv" / "bin" / "pip")
    code2, out = await asyncio.to_thread(_run, [pip, "install", "-q", "-r", str(ROOT / "requirements.txt")], 600)
    log_lines.append(f"$ pip install -r requirements.txt\n{out or 'ok'}")
    if code2 != 0:
        return JSONResponse({"ok": False, "log": "\n".join(log_lines), "message": "Code updated but a package failed to install."}, status_code=500)
    already = "Already up to date" in pull
    if not already:
        background.add_task(_exit_soon)
    return {"ok": True, "log": "\n".join(log_lines), "restarting": not already, "message": "Already up to date." if already else "Updated. Restarting now."}


@router.post("/api/system/reboot")
async def system_reboot(request: Request):
    require_pin(request)
    code, out = await asyncio.to_thread(_run, ["sudo", "-n", "/sbin/reboot"], 20)
    if code != 0:
        raise HTTPException(500, f"Reboot not permitted on this machine: {out}")
    return {"ok": True, "message": "Rebooting the Pi."}


# ---------------------------------------------------------------------------------------------
# screen on/off
# ---------------------------------------------------------------------------------------------
@router.get("/api/display")
async def display_get(request: Request):
    from .screen import desired_mode, schedule_enabled

    settings = _settings(request)
    state = request.app.state.display
    return {
        **state.summary(), "schedule_enabled": schedule_enabled(settings), "desired_now": desired_mode(settings),
        "dashboard_window": "running" if await dashboard_window_running() else "closed", "display": settings.cfg["display"],
    }


@router.post("/api/display/{action}")
async def display_set(request: Request, action: str):
    require_pin(request)
    if action in ("on", "off"):
        ok, result = await run_screen(request.app.state.display, action)
        if not ok:
            raise HTTPException(500, f"Could not turn the screen {action}: {result}")
        return {"ok": True, "message": f"Screen {action}.", "result": result}
    if action == "desktop":
        ok, result = await close_dashboard()
        if not ok:
            raise HTTPException(500, f"Could not close the dashboard window: {result}")
        return {"ok": True, "message": "The Pi is now showing its desktop. Open the dashboard again from the desktop icon or this page.", "result": result}
    if action == "dashboard":
        ok, result = await launch_dashboard(int(_settings(request).cfg["server"]["port"]))
        if not ok:
            raise HTTPException(500, f"Could not open the dashboard window: {result}")
        return {"ok": True, "message": "Opening the dashboard on the Pi's screen.", "result": result}
    raise HTTPException(404)


# ---------------------------------------------------------------------------------------------
# spotify
# ---------------------------------------------------------------------------------------------
async def _spotify_finish(request: Request, code: str, state: str) -> dict[str, Any]:
    settings = _settings(request)
    pending: dict = request.app.state.spotify_pending
    verifier = pending.pop(state, None)
    if not verifier:
        raise HTTPException(400, "That sign-in link has expired. Press Connect Spotify again and use the new link.")
    await spotify_src.exchange_code(request.app.state.client, settings, code, verifier)
    # Turn the panel on and reload so the now-playing poller starts.
    await asyncio.to_thread(write_config, settings.config_path, {"now_playing": {"provider": "spotify"}})
    from .main import reload_sources

    await reload_sources(request.app)
    return {"ok": True, "connected": True}


@router.get("/api/spotify/status")
async def spotify_status(request: Request):
    settings = _settings(request)
    tok = spotify_src.token_store(settings).read()
    source = request.app.state.sources.get("nowplaying")
    return {
        "configured": bool(settings.spotify_client_id),
        "connected": bool(tok.get("refresh_token")),
        "provider": (settings.cfg.get("now_playing") or {}).get("provider", "off"),
        "redirect_uri": spotify_src.redirect_uri(settings),
        "now": source[0].envelope() if source else None,
    }


@router.get("/api/spotify/login")
async def spotify_login(request: Request):
    require_pin(request)
    settings = _settings(request)
    if not settings.spotify_client_id:
        raise HTTPException(422, "Add your Spotify Client ID first (Settings → Keys & links).")
    verifier, challenge = spotify_src.make_pkce()
    state = secrets.token_urlsafe(16)
    pending: dict = request.app.state.spotify_pending
    pending.clear()
    pending[state] = verifier
    return {"url": spotify_src.auth_url(settings, challenge, state), "redirect_uri": spotify_src.redirect_uri(settings)}


@router.get("/api/spotify/callback")
async def spotify_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error or not code:
        return HTMLResponse(f"<h2>Spotify sign-in failed</h2><p>{error or 'no code returned'}</p>", status_code=400)
    try:
        await _spotify_finish(request, code, state)
    except HTTPException as exc:
        return HTMLResponse(f"<h2>Spotify sign-in failed</h2><p>{exc.detail}</p>", status_code=exc.status_code)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(f"<h2>Spotify sign-in failed</h2><p>{exc}</p>", status_code=500)
    return HTMLResponse("<h2>Spotify connected</h2><p>You can close this page. The dashboard shows what's playing within a few seconds.</p><p><a href='/manage#music'>Back to settings</a></p>")


@router.post("/api/spotify/paste")
async def spotify_paste(request: Request):
    require_pin(request)
    body = await request.json()
    try:
        code, state = spotify_src.parse_pasted_url(str(body.get("url", "")))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        return await _spotify_finish(request, code, state)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc)) from exc


@router.post("/api/spotify/disconnect")
async def spotify_disconnect(request: Request):
    require_pin(request)
    settings = _settings(request)
    spotify_src.token_store(settings).path.unlink(missing_ok=True)
    await asyncio.to_thread(write_config, settings.config_path, {"now_playing": {"provider": "off"}})
    from .main import reload_sources

    await reload_sources(request.app)
    return {"ok": True}
