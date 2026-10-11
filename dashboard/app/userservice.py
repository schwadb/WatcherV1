"""Run a program as a user systemd service (ChronAlert, the Spotify player) from the dashboard.

The dashboard itself runs as a system service, so talking to the user's session needs
XDG_RUNTIME_DIR / DBUS pointed at the login user. Tests set DASHBOARD_SYSTEMCTL_FAKE to a
file path: systemctl calls are then recorded there instead of run.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def home(h: Path | None = None) -> Path:
    return h or Path(os.environ.get("DASHBOARD_HOME") or Path.home())


def user_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={env['XDG_RUNTIME_DIR']}/bus")
    env.setdefault("PULSE_SERVER", f"unix:{env['XDG_RUNTIME_DIR']}/pulse/native")
    return env


def fake() -> str | None:
    return os.environ.get("DASHBOARD_SYSTEMCTL_FAKE")


def systemctl(args: list[str]) -> tuple[int, str]:
    """`systemctl --user ...` for the login user, even from a system service."""
    f = fake()
    if f is not None:
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(" ".join(args) + "\n")
        return 0, ""
    try:
        proc = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=30, env=user_env())
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return 127, "systemctl not found (this computer does not use systemd)"
    except subprocess.TimeoutExpired:
        return 124, "systemctl timed out"


class UserService:
    """A named user unit the dashboard writes, enables and watches."""

    def __init__(self, name: str, description: str, exec_start: str, extra_unit_lines: str = "", h: Path | None = None):
        self.name, self.description, self.exec_start, self.extra, self.home = name, description, exec_start, extra_unit_lines, home(h)

    @property
    def path(self) -> Path:
        return self.home / ".config/systemd/user" / f"{self.name}.service"

    def text(self) -> str:
        return f"""[Unit]
Description={self.description} (started by the Watcher dashboard)
After=network-online.target

[Service]
ExecStart={self.exec_start}
Restart=always
RestartSec=5
{self.extra}
[Install]
WantedBy=default.target
"""

    def install(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.text(), encoding="utf-8")
        code, out = systemctl(["daemon-reload"])
        if code != 0:
            raise RuntimeError(f"could not reach the user session's systemd: {out}")
        code, out = systemctl(["enable", "--now", self.name])
        if code != 0:
            raise RuntimeError(f"could not start {self.name}: {out}")
        if fake() is None:
            subprocess.run(["loginctl", "enable-linger", str(os.getuid())], capture_output=True, timeout=15)  # run before login too

    def restart(self) -> None:
        systemctl(["restart", self.name])

    def remove(self) -> None:
        if self.path.exists():
            systemctl(["disable", "--now", self.name])
            self.path.unlink()
            systemctl(["daemon-reload"])

    def status(self) -> dict:
        if not self.path.exists():
            return {"enabled": False, "running": False}
        if fake() is not None:
            return {"enabled": True, "running": True}
        code, _ = systemctl(["is-active", "--quiet", self.name])
        return {"enabled": True, "running": code == 0}
