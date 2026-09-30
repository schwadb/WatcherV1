"""Watcher Dashboard server: serves the page and keeps every data source fresh in the background.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import mock
from .cache import SourceCache, refresh_once, run_poller
from .config import Settings, load_settings
from .sources import calendar as calendar_src
from .sources import news as news_src
from .sources import photos as photos_src
from .sources import radar as radar_src
from .sources import stocks as stocks_src
from .sources import weather as weather_src

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dashboard")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STARTED = time.time()
_PHOTO_ID = re.compile(r"^[0-9a-f]{20}\.jpg$")


def build_sources(settings: Settings, client: httpx.AsyncClient) -> dict[str, tuple[SourceCache, object]]:
    """Wire each source to its cache and fetch function (real or mock)."""
    minutes = settings.minutes
    if settings.mock:
        fetchers = {
            "weather": partial(mock.weather, settings),
            "radar": partial(mock.radar, settings),
            "stocks": partial(mock.stocks, settings),
            "calendar": partial(mock.calendar, settings),
            "news": partial(mock.news, settings),
        }
    else:
        fetchers = {
            "weather": partial(weather_src.fetch, client, settings),
            "radar": partial(radar_src.fetch, client, settings),
            "stocks": partial(stocks_src.fetch, client, settings),
            "calendar": partial(calendar_src.fetch, client, settings),
            "news": partial(news_src.fetch, client, settings),
        }
    fetchers["photos"] = partial(photos_src.fetch, settings)
    intervals = {
        "weather": lambda: minutes("weather") * 60,
        "radar": lambda: minutes("radar") * 60,
        "stocks": lambda: stocks_src.interval_seconds(settings),
        "calendar": lambda: minutes("calendar") * 60,
        "news": lambda: minutes("news") * 60,
        "photos": lambda: minutes("photos", "rescan_minutes") * 60,
    }
    return {name: (SourceCache(name, intervals[name]), fetchers[name]) for name in fetchers}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    for problem in settings.errors:
        log.warning(problem)
    log.info("mock mode: %s | photos: %s | port: %s", settings.mock, settings.photo_dir, settings.cfg["server"]["port"])
    client = httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; WatcherDashboard/1.0)"})
    sources = build_sources(settings, client)
    app.state.settings = settings
    app.state.sources = sources
    tasks = [asyncio.create_task(run_poller(cache, fetch), name=f"poll-{name}") for name, (cache, fetch) in sources.items()]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await client.aclose()


app = FastAPI(title="Watcher Dashboard", lifespan=lifespan)


def _cache(name: str) -> SourceCache:
    try:
        return app.state.sources[name][0]
    except (AttributeError, KeyError) as exc:
        raise HTTPException(404, f"unknown source {name}") from exc


@app.get("/api/config")
async def api_config():
    return app.state.settings.public()


@app.get("/api/health")
async def api_health():
    sources = {name: cache.summary() for name, (cache, _) in app.state.sources.items()}
    return {"ok": all(s["ok"] for s in sources.values()), "uptime_seconds": round(time.time() - STARTED), "sources": sources}


@app.get("/api/{name}")
async def api_source(name: str):
    return JSONResponse(_cache(name).envelope())


@app.post("/api/{name}/refresh")
async def api_refresh(name: str):
    """Force a refresh now (handy after adding photos or changing .env)."""
    cache, fetch = app.state.sources[name] if name in app.state.sources else (None, None)
    if cache is None:
        raise HTTPException(404, f"unknown source {name}")
    await refresh_once(cache, fetch)
    return JSONResponse(cache.envelope())


@app.get("/photos/{filename}")
async def photo(filename: str):
    if not _PHOTO_ID.match(filename):
        raise HTTPException(404)
    path = app.state.settings.cache_dir / filename
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
