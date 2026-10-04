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

from . import manage, mock
from .pages import page_response
from .cache import SourceCache, refresh_once, run_poller
from .config import Settings, load_settings
from .sources import alerts as alerts_src
from .sources import calendar as calendar_src
from .sources import news as news_src
from .sources import photos as photos_src
from .screen import DisplayState, display_scheduler
from .sources import radar as radar_src
from .sources import spotify as spotify_src
from .sources import sports as sports_src
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
            "alerts": partial(mock.alerts, settings),
            "radar": partial(mock.radar, settings),
            "stocks": partial(mock.stocks, settings),
            "calendar": partial(mock.calendar, settings),
            "news": partial(mock.news, settings),
            "sports": partial(mock.sports, settings),
            "nowplaying": partial(mock.nowplaying, settings),
        }
    else:
        fetchers = {
            "weather": partial(weather_src.fetch, client, settings),
            "alerts": partial(alerts_src.fetch, client, settings),
            "radar": partial(radar_src.fetch, client, settings),
            "stocks": partial(stocks_src.fetch, client, settings),
            "calendar": partial(calendar_src.fetch, client, settings),
            "news": partial(news_src.fetch, client, settings),
            "sports": partial(sports_src.fetch, client, settings),
            "nowplaying": partial(spotify_src.fetch, client, settings),
        }
    fetchers["photos"] = partial(photos_src.fetch, settings)

    # Optional sources: skip entirely when the panel is off or nothing is configured.
    if not (settings.panel("alerts") and settings.cfg["weather"].get("alerts", True)):
        fetchers.pop("alerts")
    if not (settings.panel("sports") and sports_src.teams(settings)):
        fetchers.pop("sports")
    if not (settings.panel("nowplaying") and str((settings.cfg.get("now_playing") or {}).get("provider", "off")).lower() == "spotify"):
        fetchers.pop("nowplaying")
    for name in ("radar", "stocks", "calendar", "news", "photos"):
        if not settings.panel(name):
            fetchers.pop(name, None)

    intervals = {
        "weather": lambda: minutes("weather") * 60,
        "alerts": lambda: minutes("weather", "alerts_refresh_minutes") * 60,
        "radar": lambda: minutes("radar") * 60,
        "stocks": lambda: stocks_src.interval_seconds(settings),
        "calendar": lambda: minutes("calendar") * 60,
        "news": lambda: minutes("news") * 60,
        "photos": lambda: minutes("photos", "rescan_minutes") * 60,
        "sports": lambda: sports_src.refresh_minutes(settings) * 60,
        "nowplaying": lambda: 60.0,
    }
    sources = {name: (SourceCache(name, intervals[name]), fetchers[name]) for name in fetchers}
    if "sports" in sources:  # poll faster while a game is live
        cache = sources["sports"][0]
        cache.interval = lambda: sports_src.interval_seconds(settings, cache)
    if "nowplaying" in sources:  # poll fast while music plays, slowly when idle
        np_cache = sources["nowplaying"][0]
        np_cache.interval = lambda: spotify_src.interval_seconds(settings, np_cache)
    return sources


async def start_sources(app: FastAPI, settings: Settings, previous: dict | None = None) -> None:
    """(Re)build sources and pollers; carry last good data over so the screen never blanks."""
    sources = build_sources(settings, app.state.client)
    for name, (cache, _) in sources.items():
        old = (previous or {}).get(name)
        if old is not None and old[0].data is not None:
            cache.data, cache.fetched_at, cache.error = old[0].data, old[0].fetched_at, old[0].error
    app.state.settings = settings
    app.state.sources = sources
    app.state.tasks = [asyncio.create_task(run_poller(cache, fetch), name=f"poll-{name}") for name, (cache, fetch) in sources.items()]


async def stop_sources(app: FastAPI) -> None:
    tasks = getattr(app.state, "tasks", [])
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    app.state.tasks = []


async def reload_sources(app: FastAPI) -> Settings:
    """Apply edited config.yaml / .env without restarting the process."""
    async with app.state.reload_lock:
        previous = app.state.sources
        version = app.state.settings.version + 1
        settings = load_settings(override_env=True, version=version)
        for problem in settings.errors:
            log.warning(problem)
        await stop_sources(app)
        await start_sources(app, settings, previous)
        log.info("settings reloaded (version %d)", version)
        return settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    for problem in settings.errors:
        log.warning(problem)
    log.info("mock mode: %s | photos: %s | port: %s", settings.mock, settings.photo_dir, settings.cfg["server"]["port"])
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app.state.client = httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (compatible; WatcherDashboard/1.0)"})
    app.state.reload_lock = asyncio.Lock()
    app.state.sources = {}
    app.state.display = DisplayState()
    app.state.spotify_pending = {}
    await start_sources(app, settings)
    scheduler = asyncio.create_task(display_scheduler(app), name="display-scheduler")
    try:
        yield
    finally:
        scheduler.cancel()
        await asyncio.gather(scheduler, return_exceptions=True)
        await stop_sources(app)
        await app.state.client.aclose()


app = FastAPI(title="Watcher Dashboard", lifespan=lifespan)
app.state.started = STARTED
app.include_router(manage.router)  # literal routes first; the /api/{name} catch-all below comes last


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
    return {
        "ok": all(s["ok"] for s in sources.values()),
        "uptime_seconds": round(time.time() - STARTED),
        "config_version": app.state.settings.version,
        "sources": sources,
    }


# NOTE: literal /api/... routes must be declared above this catch-all or they are swallowed by it.
@app.get("/api/{name}")
async def api_source(name: str):
    return JSONResponse(_cache(name).envelope())


@app.post("/api/{name}/refresh")
async def api_refresh(name: str):
    """Force a refresh now (handy after adding photos or changing .env)."""
    if name not in app.state.sources:
        raise HTTPException(404, f"unknown source {name}")
    cache, fetch = app.state.sources[name]
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
    return page_response("index.html")


class FreshStaticFiles(StaticFiles):
    """Static files are always re-checked by the browser (ETag keeps it cheap), so an update shows up on the next load."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", FreshStaticFiles(directory=STATIC_DIR), name="static")
