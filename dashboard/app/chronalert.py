"""Start and watch the ChronAlert app (chronalert.com) from the dashboard.

ChronAlert is a separate program (a Linux AppImage) that serves its map on port 8420.
These helpers find the AppImage and keep it running as a user service (`--no-browser`,
so it never opens its own window).
"""
from __future__ import annotations

import os
from pathlib import Path

from .userservice import UserService, home

SERVICE_NAME = "chronalert"
SEARCH_DIRS = ("Applications", "Downloads", ".local/bin", "")  # relative to home


def find_appimage(h: Path | None = None) -> str | None:
    """The newest ChronAlert*.AppImage in the usual folders, or None."""
    base = home(h)
    found: list[Path] = []
    for rel in SEARCH_DIRS:
        folder = base / rel if rel else base
        if folder.is_dir():
            found.extend(p for p in folder.glob("[Cc]hron[Aa]lert*.AppImage") if p.is_file())
    if not found:
        return None
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(found[0])


def service(app_path: str = "", h: Path | None = None) -> UserService:
    return UserService(SERVICE_NAME, "ChronAlert map server", f"{app_path} --no-browser", "Environment=APPIMAGE_EXTRACT_AND_RUN=1\n", h)


def service_path(h: Path | None = None) -> Path:
    return service("", h).path


def service_text(app_path: str) -> str:
    return service(app_path).text()


def install(app_path: str, h: Path | None = None) -> str:
    """Write the user service, enable it and start it now. Returns a message for the page."""
    path = Path(app_path).expanduser()
    if not path.is_file():
        raise ValueError(f"{app_path} does not exist")
    if not os.access(path, os.X_OK):
        try:
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            raise ValueError(f"{app_path} is not executable; run: chmod +x '{app_path}'") from None
    service(str(path), h).install()
    return "ChronAlert is now started by the computer and restarted if it stops."


def remove(h: Path | None = None) -> str:
    service("", h).remove()
    return "ChronAlert is no longer started by the dashboard."


def status(h: Path | None = None) -> dict:
    return service("", h).status()
