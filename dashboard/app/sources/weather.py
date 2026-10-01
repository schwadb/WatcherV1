"""Current conditions, hourly strip, daily forecast, UV, air quality and moon phase (Open-Meteo, free, no key)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ..config import Settings
from .astro import moon_phase

log = logging.getLogger("dashboard")
API = "https://api.open-meteo.com/v1/forecast"
AIR_API = "https://air-quality-api.open-meteo.com/v1/air-quality"

# WMO weather interpretation codes -> (label, icon name). Icons live in static/icons.js.
WMO: dict[int, tuple[str, str]] = {
    0: ("Clear", "clear"),
    1: ("Mostly clear", "clear"),
    2: ("Partly cloudy", "partly-cloudy"),
    3: ("Overcast", "cloudy"),
    45: ("Fog", "fog"),
    48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "drizzle"),
    53: ("Drizzle", "drizzle"),
    55: ("Heavy drizzle", "drizzle"),
    56: ("Freezing drizzle", "sleet"),
    57: ("Freezing drizzle", "sleet"),
    61: ("Light rain", "rain"),
    63: ("Rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "sleet"),
    67: ("Freezing rain", "sleet"),
    71: ("Light snow", "snow"),
    73: ("Snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Light showers", "showers"),
    81: ("Showers", "showers"),
    82: ("Heavy showers", "showers"),
    85: ("Snow showers", "snow"),
    86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "thunder"),
    96: ("Thunderstorm, hail", "thunder"),
    99: ("Thunderstorm, hail", "thunder"),
}

AQI_BANDS = [
    (50, "Good", "#3ecf8e"), (100, "Moderate", "#f5d442"), (150, "Unhealthy for sensitive groups", "#f5a142"),
    (200, "Unhealthy", "#ff6b6b"), (300, "Very unhealthy", "#b06cff"), (10**6, "Hazardous", "#c0392b"),
]
UV_BANDS = [(3, "Low"), (6, "Moderate"), (8, "High"), (11, "Very high"), (10**6, "Extreme")]


def describe(code: Any) -> tuple[str, str]:
    try:
        return WMO.get(int(code), ("Unknown", "cloudy"))
    except (TypeError, ValueError):
        return ("Unknown", "cloudy")


def params(settings: Settings) -> dict[str, Any]:
    loc = settings.cfg["location"]
    w = settings.cfg["weather"]
    imperial = settings.imperial
    return {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "current": ",".join(
            [
                "temperature_2m", "relative_humidity_2m", "apparent_temperature", "is_day",
                "precipitation", "weather_code", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
            ]
        ),
        "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
        "forecast_hours": int(w.get("hourly_hours", 8)) + 2,
        "daily": ",".join(
            [
                "weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max",
                "sunrise", "sunset", "uv_index_max",
            ]
        ),
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh",
        "precipitation_unit": "inch" if imperial else "mm",
        "timezone": settings.timezone,
        "forecast_days": int(w["forecast_days"]) + 1,
    }


def air_params(settings: Settings) -> dict[str, Any]:
    loc = settings.cfg["location"]
    return {"latitude": loc["lat"], "longitude": loc["lon"], "current": "us_aqi,pm2_5", "timezone": settings.timezone}


def _round(value: Any) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _compass(deg: Any) -> str:
    try:
        d = float(deg)
    except (TypeError, ValueError):
        return ""
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int((d + 22.5) // 45) % 8]


def _get(block: dict, key: str, i: int) -> Any:
    values = block.get(key) or []
    return values[i] if i < len(values) else None


def uv_label(value: Any) -> dict[str, Any] | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    for limit, label in UV_BANDS:
        if v < limit:
            return {"index": round(v, 1), "label": label}
    return None


def air_summary(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    cur = raw.get("current") or {}
    aqi = _round(cur.get("us_aqi"))
    if aqi is None:
        return None
    for limit, label, color in AQI_BANDS:
        if aqi <= limit:
            return {"aqi": aqi, "pm2_5": cur.get("pm2_5"), "label": label, "color": color}
    return None


def parse(raw: dict[str, Any], settings: Settings, air: dict[str, Any] | None = None) -> dict[str, Any]:
    cur = raw.get("current", {})
    label, icon = describe(cur.get("weather_code"))
    is_day = bool(cur.get("is_day", 1))
    hours_wanted = int(settings.cfg["weather"].get("hourly_hours", 8))

    daily_raw = raw.get("daily", {})
    daily = []
    for i, date in enumerate(daily_raw.get("time", [])):
        dlabel, dicon = describe(_get(daily_raw, "weather_code", i))
        daily.append(
            {
                "date": date,
                "label": dlabel,
                "icon": dicon,
                "hi": _round(_get(daily_raw, "temperature_2m_max", i)),
                "lo": _round(_get(daily_raw, "temperature_2m_min", i)),
                "precip_pct": _round(_get(daily_raw, "precipitation_probability_max", i)),
                "sunrise": _get(daily_raw, "sunrise", i),
                "sunset": _get(daily_raw, "sunset", i),
                "uv": uv_label(_get(daily_raw, "uv_index_max", i)),
            }
        )

    hourly_raw = raw.get("hourly", {})
    now_hour = (cur.get("time") or "")[:13]  # "2026-09-30T19"
    hourly = []
    for i, t in enumerate(hourly_raw.get("time", [])):
        if now_hour and t[:13] < now_hour:
            continue
        hlabel, hicon = describe(_get(hourly_raw, "weather_code", i))
        hourly.append(
            {
                "time": t,
                "temp": _round(_get(hourly_raw, "temperature_2m", i)),
                "precip_pct": _round(_get(hourly_raw, "precipitation_probability", i)),
                "label": hlabel,
                "icon": hicon,
                "is_day": bool(_get(hourly_raw, "is_day", i)),
            }
        )
        if len(hourly) >= hours_wanted:
            break

    return {
        "location": settings.cfg["location"]["name"],
        "units": {"temp": "°F" if settings.imperial else "°C", "wind": "mph" if settings.imperial else "km/h"},
        "current": {
            "time": cur.get("time"),
            "temp": _round(cur.get("temperature_2m")),
            "feels_like": _round(cur.get("apparent_temperature")),
            "humidity": _round(cur.get("relative_humidity_2m")),
            "wind": _round(cur.get("wind_speed_10m")),
            "wind_gust": _round(cur.get("wind_gusts_10m")),
            "wind_dir": _compass(cur.get("wind_direction_10m")),
            "code": cur.get("weather_code"),
            "label": label,
            "icon": icon,
            "is_day": is_day,
        },
        "today": daily[0] if daily else None,
        "daily": daily[1:],
        "hourly": hourly,
        "air": air_summary(air),
        "moon": moon_phase(),
    }


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    want_air = bool(settings.cfg["weather"].get("air_quality", True))
    forecast_task = client.get(API, params=params(settings), timeout=15)
    if want_air:
        resp, air_resp = await asyncio.gather(forecast_task, client.get(AIR_API, params=air_params(settings), timeout=15), return_exceptions=True)
    else:
        resp, air_resp = await forecast_task, None
    if isinstance(resp, BaseException):
        raise resp
    resp.raise_for_status()
    air = None
    if isinstance(air_resp, BaseException):
        log.warning("weather: air quality fetch failed: %s", air_resp)
    elif air_resp is not None and air_resp.status_code == 200:
        air = air_resp.json()
    return parse(resp.json(), settings, air)
