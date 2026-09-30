"""Headlines from RSS feeds, merged newest-first."""
from __future__ import annotations

import asyncio
import calendar as _cal
import html
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

from ..config import Settings

_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def clean(text: str) -> str:
    return _SPACES.sub(" ", html.unescape(_TAGS.sub("", text or ""))).strip()


def parse_feed(name: str, content: bytes) -> list[dict[str, Any]]:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"{name}: could not parse feed ({parsed.bozo_exception})")
    source = name or clean(parsed.feed.get("title", "")) or "News"
    items = []
    for entry in parsed.entries:
        title = clean(entry.get("title", ""))
        if not title:
            continue
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        published = (
            datetime.fromtimestamp(_cal.timegm(stamp), tz=timezone.utc).isoformat() if stamp else None
        )
        items.append({"title": title, "source": source, "published": published, "link": entry.get("link")})
    return items


def merge(all_items: list[list[dict[str, Any]]], limit: int) -> list[dict[str, Any]]:
    """Newest-first within each feed, then round-robin across feeds so the ticker mixes sources."""
    seen: set[str] = set()
    queues = [sorted(items, key=lambda i: i["published"] or "", reverse=True) for items in all_items]
    merged: list[dict[str, Any]] = []
    while len(merged) < limit and any(queues):
        for queue in queues:
            while queue:
                item = queue.pop(0)
                key = re.sub(r"[^a-z0-9]", "", item["title"].lower())[:80]
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                break
            if len(merged) >= limit:
                break
    return merged


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    feeds = settings.cfg["news"].get("feeds") or []
    if not feeds:
        raise RuntimeError("no news feeds configured in config.yaml")
    limit = int(settings.cfg["news"]["max_headlines"])

    async def one(feed: dict[str, Any]) -> list[dict[str, Any]]:
        name = str(feed.get("name") or "")
        resp = await client.get(str(feed["url"]), timeout=20, follow_redirects=True)
        resp.raise_for_status()
        return await asyncio.to_thread(parse_feed, name, resp.content)

    results = await asyncio.gather(*(one(f) for f in feeds), return_exceptions=True)
    good, errors = [], []
    for feed, result in zip(feeds, results):
        if isinstance(result, BaseException):
            errors.append(f"{feed.get('name') or feed.get('url')}: {result}")
        else:
            good.append(result)
    if not good:
        raise RuntimeError("; ".join(errors))
    return {"headlines": merge(good, limit), "errors": errors}
