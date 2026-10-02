"""Load config.yaml and .env into one Settings object."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "location": {"name": "Plymouth, NE", "lat": 40.3039, "lon": -97.0012, "timezone": "America/Chicago"},
    "units": "imperial",
    "clock_24h": False,
    "weather": {
        "refresh_minutes": 10,
        "forecast_days": 5,
        "hourly_hours": 8,
        "air_quality": True,
        "alerts": True,
        "alerts_refresh_minutes": 5,
    },
    "radar": {
        "provider": "rainviewer",
        "refresh_minutes": 5,
        "zoom": 6,
        "frame_ms": 600,
        "basemap": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        "labels": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    },
    "stocks": {
        "symbols": {"SPY": "S&P 500", "DIA": "Dow Jones", "QQQ": "Nasdaq 100"},
        "refresh_minutes_open": 2,
        "refresh_minutes_closed": 15,
    },
    "calendar": {"days_ahead": 7, "refresh_minutes": 15, "max_events": 12},
    "calendars": [],
    "countdowns": [],
    "sports": {"refresh_minutes": 10, "teams": []},
    "news": {"refresh_minutes": 10, "max_headlines": 40, "feeds": []},
    "photos": {"folder": "photos", "seconds_per_photo": 20, "order": "shuffle", "rescan_minutes": 5, "max_size": 1920, "max_upload_mb": 25},
    "todo": {"max_items": 8},
    "now_playing": {"provider": "off", "refresh_seconds": 10},
    "panels": {
        "alerts": True, "radar": True, "stocks": True, "sports": True, "calendar": True,
        "todo": True, "news": True, "photos": True, "nowplaying": True,
    },
    "display": {"reload_at": "03:30", "screen_off": "", "screen_on": "", "dim_from": "", "dim_level": 0.5, "control": "auto", "start_at_login": True, "locked_kiosk": False},
    "server": {"host": "0.0.0.0", "port": 8080},
}

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _expand_env(value: Any) -> Any:
    """Replace ${VAR} inside strings with the environment value (empty if unset)."""
    if isinstance(value, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


@dataclass
class Settings:
    cfg: dict[str, Any]
    raw_cfg: dict[str, Any] = field(default_factory=dict)  # before ${VAR} expansion
    finnhub_key: str = ""
    ics_url: str = ""
    pin: str = ""
    spotify_client_id: str = ""
    mock: bool = False
    root: Path = ROOT
    config_path: Path = ROOT / "config.yaml"
    errors: list[str] = field(default_factory=list)
    version: int = 1

    # Convenience accessors -------------------------------------------------
    @property
    def timezone(self) -> str:
        return self.cfg["location"]["timezone"]

    @property
    def imperial(self) -> bool:
        return str(self.cfg.get("units", "imperial")).lower() != "metric"

    def minutes(self, section: str, key: str = "refresh_minutes") -> float:
        return float(self.cfg[section][key])

    def panel(self, name: str) -> bool:
        return bool((self.cfg.get("panels") or {}).get(name, True))

    @property
    def photo_dir(self) -> Path:
        folder = Path(str(self.cfg["photos"]["folder"])).expanduser()
        return folder if folder.is_absolute() else (self.root / folder)

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def fixtures_dir(self) -> Path:
        return self.root / "fixtures"

    def countdowns(self) -> list[dict[str, Any]]:
        out = []
        for entry in self.cfg.get("countdowns") or []:
            if not isinstance(entry, dict):
                continue
            try:
                when = date.fromisoformat(str(entry.get("date")))
            except (TypeError, ValueError):
                continue
            out.append({"title": str(entry.get("title") or "Countdown"), "date": when.isoformat(), "icon": str(entry.get("icon") or "")})
        return sorted(out, key=lambda c: c["date"])

    def public(self) -> dict[str, Any]:
        """The subset of settings the web page needs. Never includes secrets."""
        from .sources.calendar import calendars  # local import to avoid a cycle
        from .sources.sports import teams

        c = self.cfg
        symbols = c["stocks"]["symbols"]
        if isinstance(symbols, list):  # allow a plain list in config.yaml
            symbols = {s: s for s in symbols}
        sports_cfg = c.get("sports") if isinstance(c.get("sports"), dict) else {}
        return {
            "location": c["location"],
            "units": "imperial" if self.imperial else "metric",
            "clock_24h": bool(c.get("clock_24h", False)),
            "timezone": self.timezone,
            "intervals_seconds": {
                "weather": self.minutes("weather") * 60,
                "alerts": self.minutes("weather", "alerts_refresh_minutes") * 60,
                "radar": self.minutes("radar") * 60,
                "stocks": self.minutes("stocks", "refresh_minutes_open") * 60,
                "calendar": self.minutes("calendar") * 60,
                "news": self.minutes("news") * 60,
                "photos": self.minutes("photos", "rescan_minutes") * 60,
                "sports": float(sports_cfg.get("refresh_minutes", 10)) * 60,
                "todo": 30,
            },
            "radar": {"zoom": c["radar"]["zoom"], "frame_ms": c["radar"]["frame_ms"], "provider": c["radar"]["provider"]},
            "photos": {"seconds_per_photo": c["photos"]["seconds_per_photo"]},
            "calendar": {"days_ahead": c["calendar"]["days_ahead"], "max_events": c["calendar"]["max_events"]},
            "calendars": [{"name": cal["name"], "color": cal["color"]} for cal in calendars(self)],
            "countdowns": self.countdowns(),
            "symbols": symbols,
            "sports_enabled": bool(teams(self)) and self.panel("sports"),
            "panels": {**DEFAULTS["panels"], **(c.get("panels") or {})},
            "todo": c.get("todo") or DEFAULTS["todo"],
            "now_playing": {"provider": (c.get("now_playing") or {}).get("provider", "off"), "refresh_seconds": (c.get("now_playing") or {}).get("refresh_seconds", 10)},
            "display": c["display"],
            "reload_at": c["display"]["reload_at"],
            "mock": self.mock,
            "manage": True,
            "setup_needed": self.setup_needed(),
            "pin_required": bool(self.pin),
            "config_version": self.version,
        }

    def setup_needed(self) -> list[str]:
        """Which required secrets are still missing (drives the on-screen 'set up at…' note)."""
        from .sources.calendar import calendars

        missing = []
        if self.panel("stocks") and not self.finnhub_key:
            missing.append("FINNHUB_API_KEY")
        if self.panel("calendar") and not any(cal["url"] for cal in calendars(self)):
            missing.append("OUTLOOK_ICS_URL")
        return missing


def load_settings(config_path: str | os.PathLike | None = None, override_env: bool = False, version: int = 1) -> Settings:
    load_dotenv(ROOT / ".env", override=override_env)
    path = Path(config_path or os.environ.get("DASHBOARD_CONFIG") or ROOT / "config.yaml")
    user_cfg: dict = {}
    errors: list[str] = []
    source = path if path.exists() else (ROOT / "config.example.yaml" if (ROOT / "config.example.yaml").exists() else None)
    if source is not None:
        with open(source, encoding="utf-8") as fh:
            user_cfg = yaml.safe_load(fh) or {}
        if source != path:
            errors.append(f"{path.name} not found; using {source.name} (the settings page will create {path.name})")
    else:
        errors.append(f"config file not found: {path} (using defaults)")
    merged = _merge(DEFAULTS, user_cfg)
    cfg = _expand_env(merged)
    for entry in cfg.get("countdowns") or []:
        if isinstance(entry, dict):
            try:
                date.fromisoformat(str(entry.get("date")))
            except (TypeError, ValueError):
                errors.append(f"countdown '{entry.get('title')}' has an invalid date (use YYYY-MM-DD)")
    return Settings(
        cfg=cfg,
        raw_cfg=merged,
        config_path=path,
        finnhub_key=os.environ.get("FINNHUB_API_KEY", "").strip(),
        ics_url=os.environ.get("OUTLOOK_ICS_URL", "").strip(),
        pin=os.environ.get("DASHBOARD_PIN", "").strip(),
        spotify_client_id=os.environ.get("SPOTIFY_CLIENT_ID", "").strip(),
        mock=os.environ.get("DASHBOARD_MOCK", "0").strip().lower() in ("1", "true", "yes"),
        errors=errors,
        version=version,
    )
