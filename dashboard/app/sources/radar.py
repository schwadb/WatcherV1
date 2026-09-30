"""Animated radar frames: RainViewer (default) or Iowa State Mesonet NEXRAD (US fallback).

The server only returns the frame list and URL templates; the browser loads the tiles.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from ..config import Settings

RAINVIEWER_API = "https://api.rainviewer.com/public/weather-maps.json"
# 256px tiles, color scheme 2 (Universal Blue), smooth=1, snow=1. Zoom above 7 is upscaled by Leaflet.
RAINVIEWER_TILE = "{host}{path}/256/{z}/{x}/{y}/2/1_1.png"
RAINVIEWER_MAX_ZOOM = 7

MESONET_TILE = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/{path}/{z}/{x}/{y}.png"
MESONET_MAX_ZOOM = 10


def _base(settings: Settings) -> dict[str, Any]:
    loc = settings.cfg["location"]
    radar = settings.cfg["radar"]
    return {
        "center": [float(loc["lat"]), float(loc["lon"])],
        "zoom": int(radar["zoom"]),
        "basemap_template": radar["basemap"],
        "labels_template": radar.get("labels") or "",
        "basemap_attribution": "Map: Esri",
    }


def parse_rainviewer(raw: dict[str, Any], settings: Settings) -> dict[str, Any]:
    host = raw.get("host") or "https://tilecache.rainviewer.com"
    past = (raw.get("radar") or {}).get("past") or []
    frames = [{"time": int(f["time"]), "path": f["path"]} for f in past if "path" in f and "time" in f]
    if not frames:
        raise ValueError("RainViewer returned no radar frames")
    return {
        **_base(settings),
        "provider": "rainviewer",
        "generated": raw.get("generated"),
        "frames": frames,
        "tile_template": RAINVIEWER_TILE.replace("{host}", host),
        "max_native_zoom": RAINVIEWER_MAX_ZOOM,
        "attribution": "Radar: RainViewer.com",
    }


def mesonet_frames(now: float | None = None) -> list[dict[str, Any]]:
    now = now or time.time()
    frames = []
    for minutes in range(50, 0, -5):
        frames.append({"time": int(now - minutes * 60), "path": f"nexrad-n0q-900913-m{minutes:02d}m"})
    frames.append({"time": int(now), "path": "nexrad-n0q-900913"})
    return frames


def mesonet(settings: Settings) -> dict[str, Any]:
    return {
        **_base(settings),
        "provider": "mesonet",
        "generated": int(time.time()),
        "frames": mesonet_frames(),
        "tile_template": MESONET_TILE,
        "max_native_zoom": MESONET_MAX_ZOOM,
        "attribution": "Radar: NWS NEXRAD via Iowa State Mesonet",
    }


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    if str(settings.cfg["radar"].get("provider", "rainviewer")).lower() == "mesonet":
        return mesonet(settings)
    resp = await client.get(RAINVIEWER_API, timeout=15)
    resp.raise_for_status()
    return parse_rainviewer(resp.json(), settings)
