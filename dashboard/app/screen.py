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
                    ok, result = await run_screen(state, desired)
                    log.info("screen schedule -> %s: %s", desired, result if not ok else "ok")
            else:
                state.last_desired = None
        except Exception as exc:  # noqa: BLE001
            log.warning("screen scheduler: %s", exc)
        await asyncio.sleep(30)
