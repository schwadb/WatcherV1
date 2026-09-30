"""Photo slideshow source: scans a folder, resizes each photo once into cache/, serves the copies."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
from pathlib import Path
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


def scan(settings: Settings) -> dict[str, Any]:
    folder = settings.photo_dir
    cache = settings.cache_dir
    max_size = int(settings.cfg["photos"]["max_size"])
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS and not p.name.startswith("."))
    photos: list[dict[str, Any]] = []
    wanted_ids: set[str] = set()
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
        photos.append({"id": pid, "name": path.name, "url": f"/photos/{pid}.jpg", "w": w, "h": h})
    # remove cached copies of photos that were deleted or replaced
    if cache.exists():
        for cached in cache.glob("*.jpg"):
            if cached.stem not in wanted_ids:
                cached.unlink(missing_ok=True)
    if str(settings.cfg["photos"].get("order", "shuffle")).lower() == "shuffle":
        random.shuffle(photos)
    return {"folder": str(folder), "photos": photos, "seconds_per_photo": settings.cfg["photos"]["seconds_per_photo"]}


async def fetch(settings: Settings) -> dict[str, Any]:
    return await asyncio.to_thread(scan, settings)
