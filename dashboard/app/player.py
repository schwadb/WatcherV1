"""The Spotify Connect player on this computer: spotifyd, kept running as a user service.

spotifyd makes the computer show up as a speaker ("Dashboard") in every Spotify app, and
the dashboard can then start playback on it through the Web API. Arch/Omarchy: the
installer installs the `spotifyd` package. Debian/Raspberry Pi: download the release
tarball from github.com/Spotifyd/spotifyd into ~/.local/bin.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .userservice import UserService, home

SERVICE_NAME = "spotifyd"
ZEROCONF_PORT = 1234
DEFAULT_DEVICE_NAME = "Dashboard"


def find_spotifyd(h: Path | None = None) -> str | None:
    found = shutil.which("spotifyd")
    if found:
        return found
    local = home(h) / ".local/bin/spotifyd"
    return str(local) if local.is_file() else None


def config_path(h: Path | None = None) -> Path:
    return home(h) / ".config/spotifyd/spotifyd.conf"


def config_text(device_name: str, h: Path | None = None, volume: int = 60) -> str:
    cache = home(h) / ".cache/spotifyd"
    return f"""# Written by the Watcher dashboard (Settings -> Music). Edits here are kept until you press the button again.
[global]
device_name = "{device_name.replace(chr(34), "")}"
device_type = "t_v"
backend = "pulseaudio"
bitrate = 320
initial_volume = {int(volume)}
volume_normalisation = true
use_mpris = false
zeroconf_port = {ZEROCONF_PORT}
cache_path = "{cache}"
max_cache_size = 1000000000
"""


def service(binary: str = "spotifyd", h: Path | None = None) -> UserService:
    return UserService(SERVICE_NAME, "Spotify Connect player", f"{binary} --no-daemon", "", h)


def install(device_name: str = DEFAULT_DEVICE_NAME, h: Path | None = None) -> str:
    binary = find_spotifyd(h)
    if not binary:
        raise ValueError("spotifyd is not installed. On Omarchy/Arch run: sudo pacman -S spotifyd   (Raspberry Pi: see the README), then try again.")
    cfg = config_path(h)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(config_text(device_name or DEFAULT_DEVICE_NAME, h), encoding="utf-8")
    (home(h) / ".cache/spotifyd").mkdir(parents=True, exist_ok=True)
    service(binary, h).install()
    return f'The Spotify player is running. Pair it once: open Spotify on your phone, tap the speaker icon and choose "{device_name}".'


def remove(h: Path | None = None) -> str:
    service("spotifyd", h).remove()
    return "The Spotify player is no longer started by the dashboard."


def status(h: Path | None = None) -> dict:
    st = service("spotifyd", h).status()
    st["installed"] = bool(find_spotifyd(h))
    return st
