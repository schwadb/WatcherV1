"""Animated radar frames from one of several free sources.

  rainviewer  worldwide composite, smooth but ~2 km detail (default)
  nws         NWS hi-def base reflectivity composite, 1 km, new frame every ~2 min (US)
  nws_cref    NWS composite reflectivity (strongest echo in the column; shows storm cores) (US)
  nws_site    super-resolution data straight from the nearest NEXRAD site, ~250 m (US)
  mesonet     NWS NEXRAD composite via Iowa State Mesonet (US)

The server only returns the frame list and URL templates; the browser loads the tiles.
"""
from __future__ import annotations

import math
import re
import time
from datetime import datetime, timezone
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


# ---- NWS (opengeo.ncep.noaa.gov) WMS layers: the data radar.weather.gov itself draws ----------
NWS_WMS = "https://opengeo.ncep.noaa.gov/geoserver/{workspace}/{layer}/ows"
NWS_LAYERS = {
    "nws": ("conus", "conus_bref_qcd", "Radar: NWS hi-def (base reflectivity)"),
    "nws_cref": ("conus", "conus_cref_qcd", "Radar: NWS composite reflectivity"),
}
NWS_STATIONS_API = "https://api.weather.gov/radar/stations"
NWS_HEADERS = {"User-Agent": "WatcherDashboard/1.0 (github.com/schwadb/WatcherV1)", "Accept": "application/geo+json, application/json;q=0.9, */*;q=0.5"}
NWS_MAX_ZOOM = 12
WMS_WINDOW_MINUTES = 60
WMS_MAX_FRAMES = 15
_TIME_DIM = re.compile(r'<Dimension[^>]*name="time"[^>]*>([^<]*)</Dimension>')
PROVIDERS = ("rainviewer", "nws", "nws_cref", "nws_site", "mesonet")
_stations_cache: dict[str, Any] = {"at": 0.0, "data": None}


def parse_wms_times(xml: str) -> list[datetime]:
    """The timestamps a WMS layer offers (its time dimension), oldest first."""
    m = _TIME_DIM.search(xml)
    if not m:
        return []
    out = []
    for token in m.group(1).split(","):
        token = token.strip()
        if not token or "/" in token:  # ranges (start/end/period) are not used by these layers
            continue
        try:
            out.append(datetime.fromisoformat(token.replace("Z", "+00:00")))
        except ValueError:
            continue
    return sorted(out)


def pick_frames(times: list[datetime], now: datetime | None = None, minutes: int = WMS_WINDOW_MINUTES, max_frames: int = WMS_MAX_FRAMES) -> list[dict[str, Any]]:
    """Frames from the last `minutes`, thinned evenly to at most `max_frames`, newest last."""
    now = now or datetime.now(timezone.utc)
    recent = [t for t in times if (now - t).total_seconds() <= minutes * 60]
    if not recent:
        recent = times[-max_frames:]
    if len(recent) > max_frames:
        step = (len(recent) - 1) / (max_frames - 1)
        recent = [recent[round(i * step)] for i in range(max_frames)]
    return [{"time": int(t.timestamp()), "path": t.strftime("%Y-%m-%dT%H:%M:%S.000Z")} for t in recent]


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def nearest_site(stations: dict[str, Any], lat: float, lon: float) -> dict[str, Any] | None:
    """Closest WSR-88D (NEXRAD) site from the api.weather.gov station list."""
    best = None
    for f in stations.get("features") or []:
        props = f.get("properties") or {}
        if props.get("stationType") != "WSR-88D":
            continue
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        d = _km(lat, lon, float(coords[1]), float(coords[0]))
        if best is None or d < best["km"]:
            best = {"id": str(props.get("id") or ""), "name": str(props.get("name") or ""), "km": round(d), "lat": float(coords[1]), "lon": float(coords[0])}
    return best


async def _stations(client: httpx.AsyncClient) -> dict[str, Any]:
    if _stations_cache["data"] and time.time() - _stations_cache["at"] < 86400:
        return _stations_cache["data"]
    resp = await client.get(NWS_STATIONS_API, headers=NWS_HEADERS, timeout=20)
    resp.raise_for_status()
    _stations_cache.update(at=time.time(), data=resp.json())
    return _stations_cache["data"]


async def _wms_frames(client: httpx.AsyncClient, workspace: str, layer: str) -> list[dict[str, Any]]:
    url = NWS_WMS.format(workspace=workspace, layer=layer)
    resp = await client.get(url, params={"service": "WMS", "version": "1.3.0", "request": "GetCapabilities"}, headers=NWS_HEADERS, timeout=30)
    resp.raise_for_status()
    return pick_frames(parse_wms_times(resp.text))


def _wms_result(settings: Settings, provider: str, workspace: str, layer: str, frames: list[dict[str, Any]], attribution: str, note: str = "") -> dict[str, Any]:
    return {
        **_base(settings),
        "provider": provider,
        "generated": int(time.time()),
        "frames": frames,
        "tile_template": "",
        "wms": {"url": NWS_WMS.format(workspace=workspace, layer=layer), "layers": layer},
        "max_native_zoom": NWS_MAX_ZOOM,
        "attribution": attribution,
        "note": note,
    }


async def nws(client: httpx.AsyncClient, settings: Settings, provider: str) -> dict[str, Any]:
    """NWS composites, or the nearest radar site's super-resolution sweep (falls back to the composite)."""
    if provider == "nws_site":
        loc = settings.cfg["location"]
        site = None
        try:
            site = nearest_site(await _stations(client), float(loc["lat"]), float(loc["lon"]))
            if site:
                layer = f"{site['id'].lower()}_sr_bref"
                frames = await _wms_frames(client, site["id"].lower(), layer)
                if frames:
                    return _wms_result(settings, provider, site["id"].lower(), layer, frames, f"Radar: NWS {site['id']} {site['name']} super-res")
        except Exception as exc:  # site down or unknown: show the composite instead of nothing
            note = f"{site['id'] if site else 'nearest site'} unavailable ({exc}); showing the composite"
        else:
            note = f"{site['id'] if site else 'nearest site'} has no recent frames; showing the composite"
        workspace, layer, attribution = NWS_LAYERS["nws"]
        return _wms_result(settings, provider, workspace, layer, await _wms_frames(client, workspace, layer), attribution, note)
    workspace, layer, attribution = NWS_LAYERS[provider]
    frames = await _wms_frames(client, workspace, layer)
    if not frames:
        raise ValueError(f"NWS layer {layer} lists no radar frames")
    return _wms_result(settings, provider, workspace, layer, frames, attribution)


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    provider = str(settings.cfg["radar"].get("provider", "rainviewer")).lower()
    if provider == "mesonet":
        return mesonet(settings)
    if provider in ("nws", "nws_cref", "nws_site"):
        return await nws(client, settings, provider)
    resp = await client.get(RAINVIEWER_API, timeout=15)
    resp.raise_for_status()
    return parse_rainviewer(resp.json(), settings)
