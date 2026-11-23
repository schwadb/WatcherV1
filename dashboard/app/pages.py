"""Serve the two HTML pages with versioned links to their CSS/JS.

Phones hold on to old copies of /static/*.css and *.js. Adding ?v=<version> to those links in
the HTML (which is itself sent with no-cache) makes every update show up on the next load.
"""
from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from fastapi.responses import HTMLResponse

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_LINK = re.compile(r'(href|src)="(/static/[^"?]+\.(?:css|js))"')


@cache  # files only change with an update, which restarts the server; reload_sources clears it too
def static_version() -> str:
    """Changes whenever any stylesheet or script changes (newest file time, in seconds)."""
    newest = 0
    for p in STATIC_DIR.rglob("*"):
        if p.suffix in (".css", ".js") and p.is_file():
            newest = max(newest, int(p.stat().st_mtime))
    return format(newest, "x")


def page_html(name: str) -> str:
    html = (STATIC_DIR / name).read_text(encoding="utf-8")
    v = static_version()
    return _LINK.sub(lambda m: f'{m.group(1)}="{m.group(2)}?v={v}"', html)


# Scripts only from this server (no inline script). Images and frames may be remote: map tiles, team logos and
# album art come from other sites, and ChronAlert / the globe run on their own ports.
CSP = "; ".join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: http: https:",
    "media-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "frame-src 'self' http: https:",
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
))


def page_response(name: str) -> HTMLResponse:
    return HTMLResponse(page_html(name), headers={"Cache-Control": "no-cache", "Content-Security-Policy": CSP})
