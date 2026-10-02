"""Screen schedule: turn the TV output off at night and on in the morning by running deploy/screen.sh."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ROOT, Settings

log = logging.getLogger("dashboard")
_HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")
WINDOW_PATTERN = "--class=watcher-dashboard"   # set by deploy/kiosk.sh
AUTOSTART_LINE_MARK = "deploy/kiosk.sh"


@dataclass
class DisplayState:
    mode: str = "unknown"          # on | off | unknown
    last_desired: str | None = None
    last_command: str | None = None
    last_result: str | None = None
    last_run: float | None = None
    enabled: bool = False
    available: bool = True         # False once the script reports no display tool
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def summary(self) -> dict:
        return {
            "mode": self.mode, "enabled": self.enabled, "available": self.available,
            "last_command": self.last_command, "last_result": self.last_result, "last_run": self.last_run,
        }


def _minutes(hm: str) -> int | None:
    m = _HHMM.match((hm or "").strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def in_window(now_min: int, start: int | None, end: int | None) -> bool:
    if start is None or end is None or start == end:
        return False
    return start <= now_min < end if start < end else (now_min >= start or now_min < end)


def desired_mode(settings: Settings, now: datetime | None = None) -> str:
    d = settings.cfg["display"]
    now = now or datetime.now(ZoneInfo(settings.timezone))
    now_min = now.hour * 60 + now.minute
    return "off" if in_window(now_min, _minutes(d.get("screen_off", "")), _minutes(d.get("screen_on", ""))) else "on"


def schedule_enabled(settings: Settings) -> bool:
    d = settings.cfg["display"]
    return str(d.get("control", "auto")).lower() != "off" and _minutes(d.get("screen_off", "")) is not None and _minutes(d.get("screen_on", "")) is not None


def script_path() -> Path:
    return Path(os.environ.get("DASHBOARD_SCREEN_CMD") or ROOT / "deploy" / "screen.sh")


async def run_screen(state: DisplayState, action: str) -> tuple[bool, str]:
    """Run deploy/screen.sh on|off and record the result."""
    script = script_path()
    async with state.lock:
        state.last_command = action
        state.last_run = time.time()
        if not script.exists():
            state.last_result = f"{script.name} not found"
            state.available = False
            return False, state.last_result
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash", str(script), action, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=40)
            text = (out or b"").decode(errors="replace").strip()
            ok = proc.returncode == 0
            state.available = proc.returncode != 2
            state.last_result = text or ("ok" if ok else f"exit {proc.returncode}")
            if ok:
                state.mode = action
            return ok, state.last_result
        except (asyncio.TimeoutError, OSError) as exc:
            state.last_result = f"{type(exc).__name__}: {exc}"
            return False, state.last_result


# ---- dashboard window (desktop mode = the window is closed) ---------------------------------
async def dashboard_window_running() -> bool:
    fake = os.environ.get("DASHBOARD_WINDOW_FAKE")  # tests on a machine without a desktop
    if fake:
        return fake == "running"
    try:
        proc = await asyncio.create_subprocess_exec("pgrep", "-f", "--", WINDOW_PATTERN, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        return await proc.wait() == 0
    except OSError:
        return False


async def launch_dashboard(port: int) -> tuple[bool, str]:
    if os.environ.get("DASHBOARD_WINDOW_FAKE"):
        os.environ["DASHBOARD_WINDOW_FAKE"] = "running"
        return True, "fake dashboard window opened"
    script = ROOT / "deploy" / "kiosk.sh"
    if not script.exists():
        return False, "deploy/kiosk.sh not found"
    try:
        await asyncio.create_subprocess_exec(
            "bash", str(script), env={**os.environ, "DASHBOARD_PORT": str(port)},
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
        )
        return True, "dashboard window opening"
    except OSError as exc:
        return False, str(exc)


async def close_dashboard() -> tuple[bool, str]:
    if os.environ.get("DASHBOARD_WINDOW_FAKE"):
        os.environ["DASHBOARD_WINDOW_FAKE"] = "closed"
        return True, "fake dashboard window closed"
    try:
        proc = await asyncio.create_subprocess_exec("pkill", "-f", "--", WINDOW_PATTERN, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        code = await proc.wait()
        return code in (0, 1), "dashboard window closed" if code == 0 else "no dashboard window was open"
    except OSError as exc:
        return False, str(exc)


def autostart_target(home: Path | None = None) -> tuple[str, Path]:
    """Which login-autostart mechanism this desktop uses: (kind, file)."""
    home = home or Path(os.environ.get("DASHBOARD_HOME") or Path.home())
    hypr = home / ".config" / "hypr"
    if (hypr / "autostart.lua").exists() or (hypr / "hyprland.lua").exists():
        return "omarchy", hypr / "autostart.lua"              # Omarchy 4+: Lua config
    if (hypr / "hyprland.conf").exists():
        return "hyprland", hypr / "autostart.conf"            # plain Hyprland / Omarchy 3: exec-once
    if (home / ".config" / "labwc").exists():
        return "labwc", home / ".config" / "labwc" / "autostart"   # Raspberry Pi OS
    return "xdg", home / ".config" / "autostart" / "watcher-dashboard.desktop"  # GNOME, KDE, XFCE, Cinnamon


def set_autostart(enabled: bool, port: int, home: Path | None = None) -> str:
    """Make the dashboard open at login (or not) using this desktop's own mechanism. Idempotent."""
    kind, path = autostart_target(home)
    script = ROOT / "deploy" / "kiosk.sh"
    command = f"DASHBOARD_PORT={port} {script}"
    if kind == "xdg":
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "[Desktop Entry]\nType=Application\nName=Watcher Dashboard\n"
                f"Exec=env {command}\nIcon={ROOT / 'static' / 'icon.png'}\nTerminal=false\n"
                "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
        how = "desktop autostart entry"
    else:
        if not path.parent.exists():
            return "no desktop session found here, so nothing was set to open at login"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        kept = [ln for ln in lines if AUTOSTART_LINE_MARK not in ln]
        if enabled:
            if kind == "omarchy":
                kept.append(f'o.exec_on_start("{command}")')
            elif kind == "hyprland":
                kept.append(f"exec-once = {command}")
            else:
                kept.append(f"{command} &")
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        how = {"omarchy": "Omarchy autostart.lua", "hyprland": "Hyprland autostart.conf", "labwc": "Raspberry Pi desktop autostart"}[kind]
    return f"dashboard will open at login ({how})" if enabled else f"dashboard will not open at login ({how} entry removed; the launcher still works)"


async def display_scheduler(app) -> None:
    """Every 30 s: if the schedule's desired state changed (or at startup), run the script once."""
    state: DisplayState = app.state.display
    while True:
        try:
            settings: Settings = app.state.settings
            state.enabled = schedule_enabled(settings) and state.available
            if state.enabled:
                desired = desired_mode(settings)
                if desired != state.last_desired:  # edge-triggered so a manual override holds until the next change
                    state.last_desired = desired
                    if desired == "off" and not await dashboard_window_running():
                        log.info("screen schedule: skipping 'off' because the desktop is in use")
                    else:
                        ok, result = await run_screen(state, desired)
                        log.info("screen schedule -> %s: %s", desired, result if not ok else "ok")
            else:
                state.last_desired = None
        except Exception as exc:  # noqa: BLE001
            log.warning("screen scheduler: %s", exc)
        await asyncio.sleep(30)
