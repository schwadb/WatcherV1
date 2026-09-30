"""A tiny in-memory cache per data source, plus the background refresh loop."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

log = logging.getLogger("dashboard")

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
    last_attempt: float | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    # ---- state changes ----------------------------------------------------
    def set(self, data: Any) -> None:
        self.data = data
        self.fetched_at = time.time()
        self.error = None
        self.failures = 0

    def fail(self, exc: BaseException) -> None:
        self.error = f"{type(exc).__name__}: {exc}"[:300]
        self.failures += 1

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
            log.warning("%s: fetch failed (%d in a row): %s", cache.name, cache.failures, cache.error)


async def run_poller(cache: SourceCache, fetch: FetchFn) -> None:
    """Refresh forever. After a failure retry sooner, backing off up to the normal interval."""
    while True:
        await refresh_once(cache, fetch)
        interval = cache.interval()
        if cache.error:
            interval = min(interval, 10 * (2 ** min(cache.failures - 1, 5)))  # 10s, 20s, 40s ... up to ~5 min
        await asyncio.sleep(max(5.0, interval))
