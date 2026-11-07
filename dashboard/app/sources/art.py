"""Famous paintings for the slideshow, from the Art Institute of Chicago's free public API.

Public-domain works only (the API filters them), downloaded once into cache/art/ and served
locally, so the TV never pulls from the museum on every slide. Refreshed about once a day.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from ..config import Settings

log = logging.getLogger("dashboard")
API = "https://api.artic.edu/api/v1/artworks/search"
IIIF = "https://www.artic.edu/iiif/2/{image_id}/full/1686,/0/default.jpg"
HEADERS = {"User-Agent": "WatcherDashboard/1.0 (home dashboard; github.com/schwadb/WatcherV1)", "AIC-User-Agent": "WatcherDashboard/1.0"}
DEFAULT_ARTISTS = ["Vincent van Gogh", "Claude Monet", "Johannes Vermeer", "Rembrandt van Rijn", "Katsushika Hokusai", "Edgar Degas",
                   "Pierre-Auguste Renoir", "Paul Cézanne", "Georges Seurat", "Gustave Caillebotte", "Edward Hopper", "Georgia O'Keeffe",
                   "Mary Cassatt", "J. M. W. Turner", "Winslow Homer", "Grant Wood", "Henri de Toulouse-Lautrec", "Camille Pissarro"]
CREDIT = "Art Institute of Chicago"
PER_ARTIST_DEFAULT = 5
MAX_WORKS = 90
_ID = re.compile(r"^[0-9]{1,9}$")


def art_dir(settings: Settings) -> Path:
    return settings.cache_dir / "art"


def catalog_path(settings: Settings) -> Path:
    return art_dir(settings) / "catalog.json"


def artists(settings: Settings) -> list[str]:
    raw = (settings.cfg.get("photos") or {}).get("artists") or DEFAULT_ARTISTS
    if isinstance(raw, str):
        raw = raw.split(",")
    return [str(a).strip() for a in raw if str(a).strip()][:30]


def caption_for(work: dict[str, Any]) -> str:
    bits = [work.get("title") or "Untitled", work.get("artist") or ""]
    text = " — ".join(b for b in bits if b)
    return f"{text}, {work['date']}" if work.get("date") else text


def parse_search(raw: dict[str, Any], artist: str, limit: int) -> list[dict[str, Any]]:
    """Keep works that have an image and plausibly belong to the artist searched for."""
    out = []
    key = artist.lower().split()[-1]
    for a in raw.get("data") or []:
        if not a.get("image_id") or not a.get("title"):
            continue
        if key not in (a.get("artist_title") or "").lower():
            continue
        out.append({"id": str(a["id"]), "title": a["title"].strip(), "artist": (a.get("artist_title") or artist).strip(), "date": (a.get("date_display") or "").strip(), "image_id": a["image_id"]})
        if len(out) >= limit:
            break
    return out


def _save(resp_bytes: bytes, dest: Path, max_size: int) -> None:
    tmp = dest.with_suffix(".tmp")
    import io

    with Image.open(io.BytesIO(resp_bytes)) as im:
        im = im.convert("RGB")
        im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        im.save(tmp, "JPEG", quality=88)
    tmp.replace(dest)


async def refresh(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    """Fetch the catalogue and any missing images. Returns the catalogue (works with a local file)."""
    folder = art_dir(settings)
    folder.mkdir(parents=True, exist_ok=True)
    per_artist = int((settings.cfg.get("photos") or {}).get("art_per_artist", PER_ARTIST_DEFAULT))
    max_size = int(settings.cfg["photos"].get("max_size", 1920))
    works: list[dict[str, Any]] = []
    errors: list[str] = []
    for name in artists(settings):
        try:
            resp = await client.get(API, params={"q": name, "query[term][is_public_domain]": "true", "fields": "id,title,artist_title,date_display,image_id", "limit": 12}, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            works.extend(parse_search(resp.json(), name, per_artist))
        except Exception as exc:  # noqa: BLE001 - one artist failing must not stop the rest
            errors.append(f"{name}: {exc}")
        if len(works) >= MAX_WORKS:
            break
    kept: list[dict[str, Any]] = []
    for w in works[:MAX_WORKS]:
        dest = folder / f"{w['id']}.jpg"
        if not dest.exists():
            try:
                img = await client.get(IIIF.format(image_id=w["image_id"]), headers=HEADERS, timeout=60)
                img.raise_for_status()
                await asyncio.to_thread(_save, img.content, dest, max_size)
                await asyncio.sleep(0.5)  # be polite to the museum's image server
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{w['title'][:30]}: {exc}")
                continue
        kept.append({**w, "file": dest.name, "caption": caption_for(w), "credit": CREDIT})
    wanted = {w["file"] for w in kept}
    for old in folder.glob("*.jpg"):  # drop works by artists no longer wanted
        if old.name not in wanted and kept:
            old.unlink(missing_ok=True)
    catalog_path(settings).write_text(json.dumps({"fetched_at": time.time(), "works": kept, "errors": errors[:10]}), encoding="utf-8")
    if not kept:
        raise RuntimeError("no paintings could be fetched: " + "; ".join(errors[:3]))
    return {"count": len(kept), "works": kept, "errors": errors}


def catalog(settings: Settings) -> list[dict[str, Any]]:
    """Paintings ready to show: [{url, caption, art: True}] (empty until the first refresh)."""
    if settings.mock:
        return [{"id": f"mock{i}", "url": f"/static/mock/painting{i}.jpg", "caption": c, "art": True}
                for i, c in ((1, "Wheat Field with Cypresses — Vincent van Gogh, 1889"), (2, "Water Lilies — Claude Monet, 1906"), (3, "The Great Wave — Katsushika Hokusai, 1831"))]
    path = catalog_path(settings)
    if not path.exists():
        return []
    try:
        works = json.loads(path.read_text(encoding="utf-8")).get("works") or []
    except (OSError, ValueError):
        return []
    folder = art_dir(settings)
    return [{"id": w["id"], "url": f"/art/{w['file']}", "caption": w["caption"], "art": True} for w in works if (folder / w["file"]).exists()]


def interleave(photos: list[dict[str, Any]], paintings: list[dict[str, Any]], every: int) -> list[dict[str, Any]]:
    """One painting after every `every` photos; paintings alone when there are no photos."""
    if not paintings:
        return photos
    paintings = list(paintings)
    random.shuffle(paintings)
    if not photos:
        return paintings
    every = max(1, int(every))
    out: list[dict[str, Any]] = []
    pi = 0
    for i, p in enumerate(photos, 1):
        out.append(p)
        if i % every == 0:
            out.append(paintings[pi % len(paintings)]); pi += 1
    if pi == 0:  # fewer photos than the spacing: still show a painting each time round
        out.append(paintings[0])
    return out
