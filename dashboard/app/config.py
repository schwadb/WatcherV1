"""Load config.yaml and .env into one Settings object."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "location": {"name": "Plymouth, NE", "lat": 40.3039, "lon": -97.0012, "timezone": "America/Chicago"},
    "units": "imperial",
    "clock_24h": False,
    "weather": {"refresh_minutes": 10, "forecast_days": 5},
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
    "news": {"refresh_minutes": 10, "max_headlines": 40, "feeds": []},
    "photos": {"folder": "photos", "seconds_per_photo": 20, "order": "shuffle", "rescan_minutes": 5, "max_size": 1920},
    "display": {"reload_at": "03:30"},
    "server": {"host": "0.0.0.0", "port": 8080},
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Settings:
    cfg: dict[str, Any]
    finnhub_key: str = ""
    ics_url: str = ""
    mock: bool = False
    root: Path = ROOT
    errors: list[str] = field(default_factory=list)

    # Convenience accessors -------------------------------------------------
    @property
    def timezone(self) -> str:
        return self.cfg["location"]["timezone"]

    @property
    def imperial(self) -> bool:
        return str(self.cfg.get("units", "imperial")).lower() != "metric"

    def minutes(self, section: str, key: str = "refresh_minutes") -> float:
        return float(self.cfg[section][key])

    @property
    def photo_dir(self) -> Path:
        folder = Path(str(self.cfg["photos"]["folder"])).expanduser()
        return folder if folder.is_absolute() else (self.root / folder)

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def fixtures_dir(self) -> Path:
        return self.root / "fixtures"

    def public(self) -> dict[str, Any]:
        """The subset of settings the web page needs. Never includes secrets."""
        c = self.cfg
        symbols = c["stocks"]["symbols"]
        if isinstance(symbols, list):  # allow a plain list in config.yaml
            symbols = {s: s for s in symbols}
        return {
            "location": c["location"],
            "units": "imperial" if self.imperial else "metric",
            "clock_24h": bool(c.get("clock_24h", False)),
            "timezone": self.timezone,
            "intervals_seconds": {
                "weather": self.minutes("weather") * 60,
                "radar": self.minutes("radar") * 60,
                "stocks": self.minutes("stocks", "refresh_minutes_open") * 60,
                "calendar": self.minutes("calendar") * 60,
                "news": self.minutes("news") * 60,
                "photos": self.minutes("photos", "rescan_minutes") * 60,
            },
            "radar": {"zoom": c["radar"]["zoom"], "frame_ms": c["radar"]["frame_ms"], "provider": c["radar"]["provider"]},
            "photos": {"seconds_per_photo": c["photos"]["seconds_per_photo"]},
            "calendar": {"days_ahead": c["calendar"]["days_ahead"], "max_events": c["calendar"]["max_events"]},
            "symbols": symbols,
            "reload_at": c["display"]["reload_at"],
            "mock": self.mock,
        }


def load_settings(config_path: str | os.PathLike | None = None) -> Settings:
    load_dotenv(ROOT / ".env")
    path = Path(config_path or os.environ.get("DASHBOARD_CONFIG") or ROOT / "config.yaml")
    user_cfg: dict = {}
    errors: list[str] = []
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            user_cfg = yaml.safe_load(fh) or {}
    else:
        errors.append(f"config file not found: {path} (using defaults)")
    cfg = _merge(DEFAULTS, user_cfg)
    return Settings(
        cfg=cfg,
        finnhub_key=os.environ.get("FINNHUB_API_KEY", "").strip(),
        ics_url=os.environ.get("OUTLOOK_ICS_URL", "").strip(),
        mock=os.environ.get("DASHBOARD_MOCK", "0").strip().lower() in ("1", "true", "yes"),
        errors=errors,
    )
