"""Reach the dashboard from away from home through a Cloudflare Tunnel.

The Cloudflare side (account, domain, the tunnel itself, its public hostname and an optional
login page) is set up in Cloudflare's own dashboard; see the README. This side downloads the
`cloudflared` connector (deploy/tunnel.sh), keeps it running as a user service with the tunnel's
token, and reports whether it is connected.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import httpx

from .config import ROOT
from .userservice import UserService, home

SERVICE_NAME = "tunnel"
SCRIPT = ROOT / "deploy" / "tunnel.sh"
METRICS = "127.0.0.1:20241"  # cloudflared's local status page; /ready answers 200 once connected
HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def bin_dir(h: Path | None = None) -> Path:
    return Path(os.environ.get("TUNNEL_BIN_DIR") or (home(h) / ".local" / "share" / "watcher-dashboard" / "bin"))


def binary(h: Path | None = None) -> str:
    private = bin_dir(h) / "cloudflared"
    if private.exists():
        return str(private)
    return shutil.which("cloudflared") or ""


def installed(h: Path | None = None) -> bool:
    return bool(binary(h))


def valid_hostname(value: str) -> str:
    """"board.example.com" (lowercased, no scheme or path) or "" ; raises ValueError otherwise."""
    v = str(value or "").strip().lower()
    v = re.sub(r"^https?://", "", v).split("/")[0]
    if not v:
        return ""
    if not HOSTNAME_RE.match(v):
        raise ValueError("remote.hostname must be a name like board.example.com (no http://, no slashes)")
    return v


def service(token: str, h: Path | None = None, bin_path: str | None = None) -> UserService:
    bin_path = bin_path if bin_path is not None else (binary(h) or "cloudflared")
    extra = f"Environment=TUNNEL_TOKEN={token}\nEnvironment=TUNNEL_MANAGEMENT_DIAGNOSTICS=false\n"
    return UserService(SERVICE_NAME, "Cloudflare Tunnel (remote access to the dashboard)", f"{bin_path} tunnel --no-autoupdate --metrics {METRICS} run", extra, h)


def service_text(token: str, bin_path: str = "/usr/bin/cloudflared") -> str:
    return service(token, None, bin_path).text()


def start(token: str, h: Path | None = None) -> str:
    """Write the user service (readable only by this user: it holds the token), enable and start it."""
    if not installed(h):
        raise ValueError("cloudflared is not installed yet. Press Install first (or run: bash deploy/tunnel.sh install).")
    if not token:
        raise ValueError("Paste the tunnel token from Cloudflare first.")
    service(token, h).install(mode=0o600)
    return "The tunnel is now started by the computer and restarted if it stops."


def remove(h: Path | None = None) -> str:
    service("", h, "").remove()
    return "The tunnel is no longer started by the dashboard."


def status(h: Path | None = None) -> dict:
    return service("", h, "").status()


async def connected() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"http://{METRICS}/ready")
            return resp.status_code == 200
    except Exception:  # noqa: BLE001 - not running, or an old cloudflared without /ready
        return False
