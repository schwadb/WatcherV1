"""Stock quotes from Finnhub (free API key, 60 calls per minute)."""
from __future__ import annotations

import asyncio
from datetime import datetime, time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ..config import Settings

API = "https://finnhub.io/api/v1/quote"
NY = ZoneInfo("America/New_York")


def symbols(settings: Settings) -> dict[str, str]:
    raw = settings.cfg["stocks"]["symbols"]
    if isinstance(raw, list):
        return {str(s).upper(): str(s).upper() for s in raw}
    return {str(k).upper(): str(v) for k, v in (raw or {}).items()}


def market_open(now: datetime | None = None) -> bool:
    """Regular US session, Mon-Fri 9:30-16:00 Eastern (holidays are not tracked)."""
    now = (now or datetime.now(tz=NY)).astimezone(NY)
    if now.weekday() >= 5:
        return False
    return dtime(9, 30) <= now.time() <= dtime(16, 0)


def interval_seconds(settings: Settings) -> float:
    key = "refresh_minutes_open" if market_open() else "refresh_minutes_closed"
    return float(settings.cfg["stocks"][key]) * 60


def parse_quote(symbol: str, name: str, raw: dict[str, Any]) -> dict[str, Any]:
    price = raw.get("c")
    if not price:  # Finnhub returns all zeros for unknown symbols
        raise ValueError(f"no quote for {symbol}")
    return {
        "symbol": symbol,
        "name": name,
        "price": float(price),
        "change": float(raw.get("d") or 0.0),
        "change_pct": float(raw.get("dp") or 0.0),
        "prev_close": float(raw.get("pc") or 0.0),
        "high": raw.get("h"),
        "low": raw.get("l"),
        "quote_time": raw.get("t"),
    }


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    if not settings.finnhub_key:
        raise RuntimeError("FINNHUB_API_KEY is not set in .env (free key: https://finnhub.io/register)")
    wanted = symbols(settings)
    if not wanted:
        raise RuntimeError("no stock symbols configured in config.yaml")

    async def one(symbol: str, name: str) -> dict[str, Any]:
        resp = await client.get(API, params={"symbol": symbol, "token": settings.finnhub_key}, timeout=15)
        if resp.status_code == 401:
            raise RuntimeError("Finnhub rejected the API key (check FINNHUB_API_KEY in .env)")
        if resp.status_code == 429:
            raise RuntimeError("Finnhub rate limit hit; try fewer symbols or a longer refresh")
        resp.raise_for_status()
        return parse_quote(symbol, name, resp.json())

    results = await asyncio.gather(*(one(s, n) for s, n in wanted.items()), return_exceptions=True)
    quotes, errors = [], []
    for (symbol, _), result in zip(wanted.items(), results):
        if isinstance(result, BaseException):
            errors.append(f"{symbol}: {result}")
        else:
            quotes.append(result)
    if not quotes:
        raise RuntimeError("; ".join(errors))
    return {"market_open": market_open(), "quotes": quotes, "errors": errors}
