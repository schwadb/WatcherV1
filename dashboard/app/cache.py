"""A tiny in-memory cache per data source, plus the background refresh loop."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger("dashboard")

# ---- "is the internet down?" ----------------------------------------------------------------
OFFLINE_HINTS = ("name resolution", "name or service not known", "nodename nor servname", "network is unreachable",
                 "no route to host", "all connection attempts failed", "connecterror", "connecttimeout", "gaierror",
                 "temporarily unavailable", "no address associated")
OFFLINE_MESSAGE = "no internet connection yet (retrying)"
PROBE_HOST = "api.open-meteo.com"
_online_since: float | None = None


def describe(exc: BaseException) -> str:
    """str(exc), or the exception's type name when the message is empty (httpx connect errors often are)."""
    return str(exc).strip() or type(exc).__name__


def is_offline_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return isinstance(exc, (socket.gaierror, ConnectionError)) or any(h in text for h in OFFLINE_HINTS)


async def network_up() -> bool:
    try:
        await asyncio.get_running_loop().getaddrinfo(PROBE_HOST, 443)
        return True
    except (socket.gaierror, OSError):
        return False


async def wait_for_network(timeout: float = 120.0) -> bool:
    """Block until DNS answers (Wi-Fi often comes up after this service at boot). True when online."""
    global _online_since
    if _online_since is not None and time.time() - _online_since < 60:
        return True
    started = time.time()
    logged = False
    while True:
        if await network_up():
            _online_since = time.time()
            if logged:
                log.info("network is up after %.0fs", time.time() - started)
            return True
        if time.time() - started >= timeout:
            return False
        if not logged:
            log.info("waiting for the network before the first fetch...")
            logged = True
        await asyncio.sleep(3)

FetchFn = Callable[[], Awaitable[Any]]
IntervalFn = Callable[[], float]


@dataclass
class SourceCache:
    name: str
    interval: IntervalFn            # returns the refresh interval in seconds
    data: Any = None
    fetched_at: float | None = None  # unix time of last successful fetch
    error: str | None = None
    failures: int = 0
    offline: bool = False            # the last failure looked like "no internet", not a bad API answer
    last_attempt: float | None = None
    persist_path: Path | None = None  # where the last good data is kept across restarts (None = don't)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    # ---- state changes ----------------------------------------------------
    def set(self, data: Any) -> None:
        self.data = data
        self.fetched_at = time.time()
        self.error = None
        self.failures = 0
        self.offline = False
        self.persist()

    def fail(self, exc: BaseException) -> None:
        self.offline = is_offline_error(exc)
        self.error = OFFLINE_MESSAGE if self.offline else f"{type(exc).__name__}: {describe(exc)}"[:300]
        self.failures += 1

    # ---- remember the last good data across restarts ----------------------
    def persist(self) -> None:
        if not self.persist_path or self.data is None:
            return
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"fetched_at": self.fetched_at, "data": self.data}), encoding="utf-8")
            os.replace(tmp, self.persist_path)
        except (OSError, TypeError, ValueError) as exc:
            log.debug("%s: could not save cache: %s", self.name, exc)

    def load_persisted(self, max_age: float = 3 * 86400) -> bool:
        """Seed from the saved file when it is recent enough. The page then shows 'updated N h ago' instead of 'no data'."""
        if not self.persist_path or not self.persist_path.exists():
            return False
        try:
            saved = json.loads(self.persist_path.read_text(encoding="utf-8"))
            fetched_at = float(saved.get("fetched_at") or 0)
            if saved.get("data") is None or time.time() - fetched_at > max_age:
                return False
            self.data, self.fetched_at = saved["data"], fetched_at
            return True
        except (OSError, ValueError, TypeError):
            return False

    # ---- output -----------------------------------------------------------
    @property
    def ok(self) -> bool:
        return self.data is not None

    @property
    def age_seconds(self) -> float | None:
        return None if self.fetched_at is None else round(time.time() - self.fetched_at)

    @property
    def stale(self) -> bool:
        age = self.age_seconds
        return age is not None and age > 3 * self.interval()

    def envelope(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "source": self.name,
            "fetched_at": (
                datetime.fromtimestamp(self.fetched_at, tz=timezone.utc).isoformat() if self.fetched_at else None
            ),
            "age_seconds": self.age_seconds,
            "stale": self.stale,
            "error": self.error,
            "data": self.data,
        }

    def summary(self) -> dict[str, Any]:
        return {"ok": self.ok, "age_seconds": self.age_seconds, "stale": self.stale, "error": self.error}


async def refresh_once(cache: SourceCache, fetch: FetchFn) -> None:
    """Run one fetch; on failure keep the last good data and record the error."""
    async with cache._lock:
        cache.last_attempt = time.time()
        try:
            data = await fetch()
            cache.set(data)
            log.info("%s: refreshed", cache.name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad source must never take down the rest
            cache.fail(exc)
            log.warning("%s: fetch failed (%d in a row): %s%s", cache.name, cache.failures, cache.error,
                        f" [{type(exc).__name__}: {describe(exc)[:200]}]" if cache.offline else "")


def next_interval(cache: SourceCache) -> float:
    """Seconds until the next attempt: the normal interval, a short fixed retry while offline, or backoff after API errors."""
    interval = cache.interval()
    if cache.error and cache.offline:
        interval = min(interval, 10.0 if cache.failures < 4 else 30.0)  # notice the internet coming back quickly
    elif cache.error:
        interval = min(interval, 10 * (2 ** min(cache.failures - 1, 5)))  # 10s, 20s, 40s ... up to ~5 min
    return max(5.0, interval)


async def run_poller(cache: SourceCache, fetch: FetchFn, wait_network: bool = True) -> None:
    """Refresh forever. Waits for the network before the very first fetch; retries fast while offline."""
    if wait_network:
        await wait_for_network()
    while True:
        await refresh_once(cache, fetch)
        await asyncio.sleep(next_interval(cache))
