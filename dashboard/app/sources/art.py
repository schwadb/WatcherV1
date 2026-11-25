"""Famous paintings for the slideshow, from museums with free open-access APIs (no keys).

Sources: the Art Institute of Chicago, The Metropolitan Museum of Art and the Cleveland Museum
of Art. Public-domain works only (each API filters them), downloaded once into cache/art/ and
served locally, so the TV never pulls from a museum on every slide. Refreshed about once a day.
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
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}"
CMA_SEARCH = "https://openaccess-api.clevelandart.org/api/artworks/"
PROVIDERS = {"aic": "Art Institute of Chicago", "met": "The Metropolitan Museum of Art", "cma": "Cleveland Museum of Art"}
HEADERS = {"User-Agent": "WatcherDashboard/1.0 (home dashboard; github.com/schwadb/WatcherV1)", "AIC-User-Agent": "WatcherDashboard/1.0"}
DEFAULT_ARTISTS = ["Vincent van Gogh", "Claude Monet", "Johannes Vermeer", "Rembrandt van Rijn", "Katsushika Hokusai", "Edgar Degas",
                   "Pierre-Auguste Renoir", "Paul Cézanne", "Georges Seurat", "Gustave Caillebotte", "Edward Hopper", "Georgia O'Keeffe",
                   "Mary Cassatt", "J. M. W. Turner", "Winslow Homer", "Grant Wood", "Henri de Toulouse-Lautrec", "Camille Pissarro"]
CREDIT = "Art Institute of Chicago"
PER_ARTIST_DEFAULT = 5
MAX_WORKS = 120
_ID = re.compile(r"^[0-9]{1,9}$")


def sources(settings: Settings) -> list[str]:
    """Which museums to draw from (Settings → Photos); all three unless narrowed."""
    raw = (settings.cfg.get("photos") or {}).get("art_sources")
    if isinstance(raw, str):
        raw = raw.split(",")
    chosen = [str(x).strip().lower() for x in (raw or []) if str(x).strip().lower() in PROVIDERS]
    return chosen or list(PROVIDERS)


def _by(artist: str, name: str) -> bool:
    return artist.lower().split()[-1] in (name or "").lower()


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
    """Art Institute of Chicago: keep works that have an image and plausibly belong to the artist searched for."""
    out = []
    for a in raw.get("data") or []:
        if not a.get("image_id") or not a.get("title") or not _by(artist, a.get("artist_title")):
            continue
        out.append({"id": f"aic-{a['id']}", "title": a["title"].strip(), "artist": (a.get("artist_title") or artist).strip(), "date": (a.get("date_display") or "").strip(),
                    "image": IIIF.format(image_id=a["image_id"]), "credit": PROVIDERS["aic"]})
        if len(out) >= limit:
            break
    return out


def parse_met_object(obj: dict[str, Any], artist: str) -> dict[str, Any] | None:
    """The Met: one object record -> a work, or None when it is not a public-domain image by that artist."""
    if not obj.get("isPublicDomain") or not obj.get("primaryImageSmall") or not obj.get("title") or not _by(artist, obj.get("artistDisplayName")):
        return None
    return {"id": f"met-{obj['objectID']}", "title": str(obj["title"]).strip(), "artist": str(obj.get("artistDisplayName") or artist).strip(),
            "date": str(obj.get("objectDate") or "").strip(), "image": obj["primaryImageSmall"], "credit": PROVIDERS["met"]}


def parse_cma(raw: dict[str, Any], artist: str, limit: int) -> list[dict[str, Any]]:
    """Cleveland Museum of Art open-access search -> works (CC0 with a web image)."""
    out = []
    for a in raw.get("data") or []:
        image = ((a.get("images") or {}).get("web") or {}).get("url")
        creators = a.get("creators") or []
        who = str((creators[0].get("description") if creators else "") or "").split(" (")[0].strip()
        if not image or not a.get("title") or not _by(artist, who):
            continue
        out.append({"id": f"cma-{a['id']}", "title": str(a["title"]).strip(), "artist": who or artist, "date": str(a.get("creation_date") or "").strip(),
                    "image": image, "credit": PROVIDERS["cma"]})
        if len(out) >= limit:
            break
    return out


async def search_aic(client: httpx.AsyncClient, artist: str, limit: int) -> list[dict[str, Any]]:
    resp = await client.get(API, params={"q": artist, "query[term][is_public_domain]": "true", "fields": "id,title,artist_title,date_display,image_id", "limit": 12}, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return parse_search(resp.json(), artist, limit)


async def search_met(client: httpx.AsyncClient, artist: str, limit: int) -> list[dict[str, Any]]:
    resp = await client.get(MET_SEARCH, params={"q": artist, "hasImages": "true", "isPublicDomain": "true", "artistOrCulture": "true"}, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    out: list[dict[str, Any]] = []
    for object_id in (resp.json().get("objectIDs") or [])[:14]:
        try:
            obj = await client.get(MET_OBJECT.format(id=int(object_id)), headers=HEADERS, timeout=20)
            obj.raise_for_status()
            work = parse_met_object(obj.json(), artist)
        except Exception:  # noqa: BLE001 - one odd record must not stop the rest
            continue
        if work:
            out.append(work)
        if len(out) >= limit:
            break
    return out


async def search_cma(client: httpx.AsyncClient, artist: str, limit: int) -> list[dict[str, Any]]:
    resp = await client.get(CMA_SEARCH, params={"artists": artist, "has_image": 1, "cc0": 1, "type": "Painting", "limit": 12, "fields": "id,title,creators,creation_date,images"}, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return parse_cma(resp.json(), artist, limit)


SEARCHERS = {"aic": search_aic, "met": search_met, "cma": search_cma}


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
    chosen = sources(settings)
    share = max(1, -(-per_artist // len(chosen)))  # each museum contributes its share of the per-artist count
    for name in artists(settings):
        for key in chosen:
            try:
                works.extend(await SEARCHERS[key](client, name, share))
            except Exception as exc:  # noqa: BLE001 - one museum or artist failing must not stop the rest
                errors.append(f"{name} ({key}): {exc}")
        if len(works) >= MAX_WORKS:
            break
    kept: list[dict[str, Any]] = []
    for w in works[:MAX_WORKS]:
        dest = folder / f"{w['id']}.jpg"
        if not dest.exists():
            try:
                img = await client.get(w["image"], headers=HEADERS, timeout=60)
                img.raise_for_status()
                await asyncio.to_thread(_save, img.content, dest, max_size)
                await asyncio.sleep(0.5)  # be polite to the museums' image servers
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{w['title'][:30]}: {exc}")
                continue
        kept.append({**w, "file": dest.name, "caption": caption_for(w)})
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
        return [{"id": f"mock{i}", "url": f"/static/mock/painting{i}.jpg", "caption": c, "credit": cr, "art": True}
                for i, c, cr in ((1, "Wheat Field with Cypresses — Vincent van Gogh, 1889", PROVIDERS["met"]), (2, "Water Lilies — Claude Monet, 1906", PROVIDERS["aic"]), (3, "The Great Wave — Katsushika Hokusai, 1831", PROVIDERS["cma"]))]
    path = catalog_path(settings)
    if not path.exists():
        return []
    try:
        works = json.loads(path.read_text(encoding="utf-8")).get("works") or []
    except (OSError, ValueError):
        return []
    folder = art_dir(settings)
    return [{"id": w["id"], "url": f"/art/{w['file']}", "caption": w["caption"], "credit": w.get("credit") or "Art Institute of Chicago", "art": True} for w in works if (folder / w["file"]).exists()]


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
