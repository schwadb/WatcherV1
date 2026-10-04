"""Start and watch the ChronAlert app (chronalert.com) from the dashboard.

ChronAlert is a separate program (a Linux AppImage) that serves its map on port 8420.
These helpers find the AppImage, write a user systemd service that keeps it running
(`--no-browser`, so it never opens its own window), and report whether it is running.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

SERVICE_NAME = "chronalert"
SEARCH_DIRS = ("Applications", "Downloads", ".local/bin", "")  # relative to home


def _home(home: Path | None = None) -> Path:
    return home or Path(os.environ.get("DASHBOARD_HOME") or Path.home())


def find_appimage(home: Path | None = None) -> str | None:
    """The newest ChronAlert*.AppImage in the usual folders, or None."""
    base = _home(home)
    found: list[Path] = []
    for rel in SEARCH_DIRS:
        folder = base / rel if rel else base
        if folder.is_dir():
            found.extend(p for p in folder.glob("[Cc]hron[Aa]lert*.AppImage") if p.is_file())
    if not found:
        return None
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(found[0])


def service_path(home: Path | None = None) -> Path:
    return _home(home) / ".config/systemd/user" / f"{SERVICE_NAME}.service"


def service_text(app_path: str) -> str:
    return f"""[Unit]
Description=ChronAlert map server (started by the Watcher dashboard)
After=network-online.target

[Service]
ExecStart={app_path} --no-browser
Restart=always
RestartSec=5
Environment=APPIMAGE_EXTRACT_AND_RUN=1

[Install]
WantedBy=default.target
"""


def _systemctl(args: list[str], home: Path | None = None) -> tuple[int, str]:
    """Run `systemctl --user ...` for the login user, even from a system service."""
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={env['XDG_RUNTIME_DIR']}/bus")
    fake = os.environ.get("DASHBOARD_SYSTEMCTL_FAKE")
    if fake is not None:  # tests: pretend it worked and remember the call
        Path(fake).write_text(" ".join(args) + "\n", encoding="utf-8")
        return 0, ""
    try:
        proc = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=30, env=env)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return 127, "systemctl not found (this computer does not use systemd)"
    except subprocess.TimeoutExpired:
        return 124, "systemctl timed out"


def install(app_path: str, home: Path | None = None) -> str:
    """Write the user service, enable it and start it now. Returns a message for the page."""
    path = Path(app_path).expanduser()
    if not path.is_file():
        raise ValueError(f"{app_path} does not exist")
    if not os.access(path, os.X_OK):
        try:
            path.chmod(path.stat().st_mode | 0o111)
        except OSError:
            raise ValueError(f"{app_path} is not executable; run: chmod +x '{app_path}'") from None
    unit = service_path(home)
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(service_text(str(path)), encoding="utf-8")
    code, out = _systemctl(["daemon-reload"], home)
    if code != 0:
        raise RuntimeError(f"could not reach the user session's systemd: {out}")
    code, out = _systemctl(["enable", "--now", SERVICE_NAME], home)
    if code != 0:
        raise RuntimeError(f"could not start ChronAlert: {out}")
    if os.environ.get("DASHBOARD_SYSTEMCTL_FAKE") is None:
        subprocess.run(["loginctl", "enable-linger", str(os.getuid())], capture_output=True, timeout=15)  # run before login too
    return "ChronAlert is now started by the computer and restarted if it stops."


def remove(home: Path | None = None) -> str:
    unit = service_path(home)
    if unit.exists():
        _systemctl(["disable", "--now", SERVICE_NAME], home)
        unit.unlink()
        _systemctl(["daemon-reload"], home)
    return "ChronAlert is no longer started by the dashboard."


def status(home: Path | None = None) -> dict:
    """{'enabled': bool, 'running': bool} for the user service."""
    unit = service_path(home)
    if not unit.exists():
        return {"enabled": False, "running": False}
    if os.environ.get("DASHBOARD_SYSTEMCTL_FAKE") is not None:
        return {"enabled": True, "running": True}
    code, _ = _systemctl(["is-active", "--quiet", SERVICE_NAME], home)
    return {"enabled": True, "running": code == 0}
