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


# ---- finding feeds (used by the settings page) ---------------------------------------------
# Checked live when this list was written; the settings page lets the user add any of them with one tap.
FEED_CATALOG: list[dict[str, Any]] = [
    {"group": "National", "feeds": [
        {"name": "NPR", "url": "https://feeds.npr.org/1001/rss.xml"},
        {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
        {"name": "CBS News", "url": "https://www.cbsnews.com/latest/rss/main"},
        {"name": "ABC News", "url": "https://abcnews.go.com/abcnews/topstories"},
        {"name": "NBC News", "url": "https://feeds.nbcnews.com/nbcnews/public/news"},
        {"name": "CNN", "url": "http://rss.cnn.com/rss/cnn_topstories.rss"},
        {"name": "Fox News", "url": "https://moxie.foxnews.com/google-publisher/latest.xml"},
        {"name": "New York Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"},
        {"name": "Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
        {"name": "Washington Post", "url": "https://feeds.washingtonpost.com/rss/national"},
        {"name": "PBS NewsHour", "url": "https://www.pbs.org/newshour/feeds/rss/headlines"},
        {"name": "The Hill", "url": "https://thehill.com/feed/"},
        {"name": "Politico", "url": "https://rss.politico.com/politics-news.xml"},
    ]},
    {"group": "Nebraska", "feeds": [
        {"name": "Omaha World-Herald", "url": "https://omaha.com/search/?f=rss&t=article&l=50&s=start_time&sd=desc"},
        {"name": "Lincoln Journal Star", "url": "https://journalstar.com/search/?f=rss&t=article&l=50&s=start_time&sd=desc"},
        {"name": "KETV Omaha", "url": "https://www.ketv.com/topstories-rss"},
        {"name": "WOWT Omaha", "url": "https://www.wowt.com/arc/outboundfeeds/rss/?outputType=xml"},
        {"name": "10/11 Now Lincoln", "url": "https://www.1011now.com/arc/outboundfeeds/rss/?outputType=xml"},
        {"name": "Nebraska Examiner", "url": "https://nebraskaexaminer.com/feed/"},
        {"name": "Flatwater Free Press", "url": "https://flatwaterfreepress.org/feed/"},
    ]},
    {"group": "Business", "feeds": [
        {"name": "MarketWatch", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
        {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
        {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss"},
        {"name": "Fortune", "url": "https://fortune.com/feed/"},
    ]},
    {"group": "Sports", "feeds": [
        {"name": "ESPN", "url": "https://www.espn.com/espn/rss/news"},
        {"name": "ESPN College Football", "url": "https://www.espn.com/espn/rss/ncf/news"},
        {"name": "ESPN NFL", "url": "https://www.espn.com/espn/rss/nfl/news"},
        {"name": "Huskers.com", "url": "https://huskers.com/rss"},
        {"name": "CBS Sports", "url": "https://www.cbssports.com/rss/headlines/"},
        {"name": "Yahoo Sports", "url": "https://sports.yahoo.com/rss/"},
    ]},
    {"group": "Weather, space & radio", "feeds": [
        {"name": "NWS alerts for Nebraska", "url": "https://api.weather.gov/alerts/active.atom?area=NE"},
        {"name": "ARRL News (ham radio)", "url": "https://www.arrl.org/news/rss"},
        {"name": "NASA", "url": "https://www.nasa.gov/news-release/feed/"},
    ]},
    {"group": "Tech & science", "feeds": [
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
        {"name": "Wired", "url": "https://www.wired.com/feed/rss"},
        {"name": "Hacker News", "url": "https://hnrss.org/frontpage"},
        {"name": "Science Daily", "url": "https://www.sciencedaily.com/rss/top.xml"},
    ]},
]

FIND_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) WatcherDashboard/1.0", "Accept": "*/*"}
COMMON_FEED_PATHS = ("/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml", "/index.xml", "/atom.xml", "/feeds/posts/default")
_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r"""([a-zA-Z:-]+)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""")


def feed_links_in_html(html_text: str, base_url: str) -> list[str]:
    """Feed addresses advertised by a web page (<link rel="alternate" type="application/rss+xml">)."""
    from urllib.parse import urljoin

    out: list[str] = []
    for tag in _LINK_TAG.findall(html_text):
        attrs = {m.group(1).lower(): (m.group(3) or m.group(4) or m.group(5) or "") for m in _ATTR.finditer(tag)}
        rel = attrs.get("rel", "").lower()
        typ = attrs.get("type", "").lower()
        href = attrs.get("href", "")
        if href and "alternate" in rel and ("rss" in typ or "atom" in typ or "xml" in typ):
            out.append(urljoin(base_url, href))
    return out


def feed_summary(content: bytes) -> dict[str, Any] | None:
    """{'title', 'sample'} when the bytes parse as a feed with at least one entry, else None."""
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        return None
    if not parsed.entries:
        return None
    return {"title": clean(parsed.feed.get("title", "")), "sample": clean(parsed.entries[0].get("title", ""))}


async def find_feed(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """Turn any website or feed address into {'name', 'url', 'sample'}; raises LookupError when none is found."""
    from urllib.parse import urlsplit

    url = url.strip()
    starts = [url] if url.startswith(("http://", "https://")) else ["https://" + url, "http://" + url]  # no scheme typed: try both
    tried: list[str] = []

    async def get(u: str) -> httpx.Response | None:
        tried.append(u)
        try:
            resp = await client.get(u, headers=FIND_HEADERS, timeout=12, follow_redirects=True)
            return resp if resp.status_code == 200 else None
        except Exception:
            return None

    first = None
    for url in starts:
        first = await get(url)
        if first is not None:
            break
    if first is not None:
        summary = feed_summary(first.content)
        if summary:  # it already is a feed
            return {"name": summary["title"], "url": str(first.url), "sample": summary["sample"]}
        candidates = feed_links_in_html(first.text[:400_000], str(first.url))
    else:
        candidates = []
    parts = urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}"
    for path in COMMON_FEED_PATHS:
        if root + path not in candidates:
            candidates.append(root + path)
    for cand in candidates[:12]:
        resp = await get(cand)
        if resp is None:
            continue
        summary = feed_summary(resp.content)
        if summary:
            return {"name": summary["title"], "url": str(resp.url), "sample": summary["sample"]}
    raise LookupError("No news feed found on that site. Try searching for \"<site name> RSS\" and paste the feed address instead.")
