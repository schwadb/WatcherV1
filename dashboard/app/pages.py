"""Serve the two HTML pages with versioned links to their CSS/JS.

Phones hold on to old copies of /static/*.css and *.js. Adding ?v=<version> to those links in
the HTML (which is itself sent with no-cache) makes every update show up on the next load.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi.responses import HTMLResponse

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_LINK = re.compile(r'(href|src)="(/static/[^"?]+\.(?:css|js))"')


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


def page_response(name: str) -> HTMLResponse:
    return HTMLResponse(page_html(name), headers={"Cache-Control": "no-cache"})
