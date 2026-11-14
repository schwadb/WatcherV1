"""Photo slideshow source: scans a folder, resizes each photo once into cache/, serves the copies."""
from __future__ import annotations

import asyncio
import json
import hashlib
import logging
import os
import random
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from PIL import Image, ImageOps

from ..config import Settings

log = logging.getLogger("dashboard")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def photo_id(path: Path, root: Path) -> str:
    stat = path.stat()
    key = f"{path.relative_to(root)}|{int(stat.st_mtime)}|{stat.st_size}"
    return hashlib.sha1(key.encode()).hexdigest()[:20]


def resize_into_cache(src: Path, dest: Path, max_size: int) -> tuple[int, int]:
    """Rotate per EXIF, shrink so the longest edge is max_size, save as JPEG. Returns (w, h)."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im) or im
        im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f"{dest.stem}.{os.getpid()}.tmp")
        im.save(tmp, "JPEG", quality=85, optimize=True)
        tmp.replace(dest)
        return im.size


# ---------------------------------------------------------------------------------------------
# captions: when and where a photo was taken (from the original file's EXIF), "on this day" memories
# ---------------------------------------------------------------------------------------------
EXIF_IFD, GPS_IFD = 0x8769, 0x8825
TAG_DATETIME_ORIGINAL, TAG_DATETIME = 0x9003, 0x0132
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
GEOCODE_PER_SCAN = 5
MEMORY_WINDOW_DAYS = 3


def _to_deg(values: Any, ref: Any) -> float | None:
    try:
        d, m, sec = (float(v) for v in values)
    except (TypeError, ValueError):
        return None
    deg = d + m / 60 + sec / 3600
    return -deg if str(ref).upper() in ("S", "W") else deg


def exif_info(path: Path) -> dict[str, Any]:
    """{"taken": "YYYY-MM-DD" | None, "lat": float | None, "lon": float | None} from the original file."""
    out: dict[str, Any] = {"taken": None, "lat": None, "lon": None}
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            raw = exif.get_ifd(EXIF_IFD).get(TAG_DATETIME_ORIGINAL) or exif.get(TAG_DATETIME)
            if raw and len(str(raw)) >= 10:
                y, mo, d = str(raw)[:10].replace("-", ":").split(":")[:3]
                if y.isdigit() and 1900 < int(y) < 2200:
                    out["taken"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            gps = exif.get_ifd(GPS_IFD)
            if gps:
                lat = _to_deg(gps.get(2), gps.get(1))
                lon = _to_deg(gps.get(4), gps.get(3))
                if lat is not None and lon is not None and (lat or lon):
                    out["lat"], out["lon"] = round(lat, 5), round(lon, 5)
    except Exception as exc:  # noqa: BLE001 - a photo without readable EXIF is normal
        log.debug("photos: no EXIF for %s: %s", path.name, exc)
    return out


def place_name(address: dict[str, Any]) -> str:
    """"Lincoln, Nebraska" from a Nominatim address block (town + state; country when outside the US)."""
    town = next((address.get(k) for k in ("city", "town", "village", "hamlet", "municipality", "county") if address.get(k)), "")
    region = address.get("state") or ""
    country = address.get("country") or ""
    if (address.get("country_code") or "").lower() == "us":
        return ", ".join(x for x in (town, region) if x)
    return ", ".join(x for x in (town, country or region) if x)


def _geo_key(lat: float, lon: float) -> str:
    return f"{round(lat, 2)},{round(lon, 2)}"


def lookup_places(meta: dict[str, dict[str, Any]], places: dict[str, str], limit: int = GEOCODE_PER_SCAN) -> int:
    """Reverse-geocode up to `limit` new spots (Nominatim asks for one request a second). Returns how many were looked up."""
    import time as _time
    import httpx

    done = 0
    for info in meta.values():
        if info.get("lat") is None or done >= limit:
            continue
        key = _geo_key(info["lat"], info["lon"])
        if key in places:
            continue
        try:
            resp = httpx.get(NOMINATIM, params={"lat": info["lat"], "lon": info["lon"], "format": "jsonv2", "zoom": 10},
                             headers={"User-Agent": "WatcherDashboard/1.0 (self-hosted photo captions)"}, timeout=10)
            places[key] = place_name(resp.json().get("address") or {}) if resp.status_code == 200 else ""
        except Exception as exc:  # noqa: BLE001 - offline: try again next scan
            log.info("photos: place lookup skipped (%s)", exc)
            break
        done += 1
        _time.sleep(1.1)
    return done


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def is_memory(taken: str | None, today: str, window: int = MEMORY_WINDOW_DAYS) -> bool:
    """Taken within ±window days of today's date in an earlier year."""
    if not taken:
        return False
    try:
        t = date.fromisoformat(taken)
        now = date.fromisoformat(today)
    except ValueError:
        return False
    if t.year >= now.year:
        return False
    try:
        anniversary = t.replace(year=now.year)
    except ValueError:  # Feb 29
        anniversary = now.replace(month=3, day=1)
    return abs((anniversary - now).days) <= window


def caption_for_photo(taken: str | None, place: str, today: str | None = None) -> str:
    """"Lincoln, Nebraska · July 2019" (the page adds an "On this day" tag for memories), or ""."""
    when = ""
    if taken:
        try:
            t = date.fromisoformat(taken)
            when = f"{MONTHS[t.month - 1]} {t.year}"
        except ValueError:
            when = ""
    return " · ".join(x for x in (place, when) if x)


def load_meta(cache_dir: Path) -> dict[str, Any]:
    path = cache_dir / "photo-meta.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"photos": {}, "places": {}}
    except (FileNotFoundError, ValueError):
        return {"photos": {}, "places": {}}


def save_meta(cache_dir: Path, data: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f"photo-meta.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(cache_dir / "photo-meta.json")


def scan(settings: Settings) -> dict[str, Any]:
    folder = settings.photo_dir
    cache = settings.cache_dir
    max_size = int(settings.cfg["photos"]["max_size"])
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS and not p.name.startswith("."))
    photos: list[dict[str, Any]] = []
    wanted_ids: set[str] = set()
    want_captions = bool(settings.cfg["photos"].get("captions", True))
    want_memories = bool(settings.cfg["photos"].get("memories", True))
    meta = load_meta(cache) if (want_captions or want_memories) else {"photos": {}, "places": {}}
    meta_changed = False
    today = datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
    for path in files:
        pid = photo_id(path, folder)
        wanted_ids.add(pid)
        dest = cache / f"{pid}.jpg"
        try:
            if not dest.exists():
                w, h = resize_into_cache(path, dest, max_size)
            else:
                with Image.open(dest) as im:
                    w, h = im.size
        except Exception as exc:  # noqa: BLE001 - skip a broken file, keep the rest
            log.warning("photos: skipping %s: %s", path.name, exc)
            continue
        if (want_captions or want_memories) and pid not in meta["photos"]:
            meta["photos"][pid] = exif_info(path)
            meta_changed = True
        photos.append({"id": pid, "name": path.name, "url": f"/photos/{pid}.jpg", "w": w, "h": h})
    if want_captions and not settings.mock:
        places = meta.setdefault("places", {})
        if lookup_places({pid: meta["photos"][pid] for pid in wanted_ids if pid in meta["photos"]}, places):
            meta_changed = True
    if meta_changed or any(pid not in wanted_ids for pid in list(meta.get("photos", {}))):
        meta["photos"] = {pid: v for pid, v in meta.get("photos", {}).items() if pid in wanted_ids}
        save_meta(cache, meta)
    for photo in photos:
        info = meta.get("photos", {}).get(photo["id"]) or {}
        place = meta.get("places", {}).get(_geo_key(info["lat"], info["lon"]), "") if info.get("lat") is not None else ""
        photo["memory"] = want_memories and is_memory(info.get("taken"), today)
        photo["caption"] = caption_for_photo(info.get("taken"), place, today) if want_captions else ""
        photo["credit"] = ""
    # remove cached copies of photos that were deleted or replaced
    if cache.exists():
        for cached in cache.glob("*.jpg"):
            if cached.stem not in wanted_ids:
                cached.unlink(missing_ok=True)
    if str(settings.cfg["photos"].get("order", "shuffle")).lower() == "shuffle":
        random.shuffle(photos)
    if want_memories:  # today's memories lead the show
        photos = [p for p in photos if p.get("memory")] + [p for p in photos if not p.get("memory")]
    paintings = []
    if settings.cfg["photos"].get("art", True):
        from . import art

        paintings = art.catalog(settings)
        photos = art.interleave(photos, paintings, int(settings.cfg["photos"].get("art_every", 4) or 4))
    return {"folder": str(folder), "photos": photos, "paintings": len(paintings), "memories": sum(1 for p in photos if p.get("memory")),
            "seconds_per_photo": settings.cfg["photos"]["seconds_per_photo"]}


async def fetch(settings: Settings) -> dict[str, Any]:
    return await asyncio.to_thread(scan, settings)
