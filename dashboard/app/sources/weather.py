"""Current conditions and daily forecast from Open-Meteo (free, no key)."""
from __future__ import annotations

from typing import Any

import httpx

from ..config import Settings

API = "https://api.open-meteo.com/v1/forecast"

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


def describe(code: Any) -> tuple[str, str]:
    try:
        return WMO.get(int(code), ("Unknown", "cloudy"))
    except (TypeError, ValueError):
        return ("Unknown", "cloudy")


def params(settings: Settings) -> dict[str, Any]:
    loc = settings.cfg["location"]
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
        "daily": ",".join(
            ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_probability_max", "sunrise", "sunset"]
        ),
        "temperature_unit": "fahrenheit" if imperial else "celsius",
        "wind_speed_unit": "mph" if imperial else "kmh",
        "precipitation_unit": "inch" if imperial else "mm",
        "timezone": settings.timezone,
        "forecast_days": int(settings.cfg["weather"]["forecast_days"]) + 1,
    }


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


def parse(raw: dict[str, Any], settings: Settings) -> dict[str, Any]:
    cur = raw.get("current", {})
    label, icon = describe(cur.get("weather_code"))
    is_day = bool(cur.get("is_day", 1))
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
            }
        )
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
    }


def _get(block: dict, key: str, i: int) -> Any:
    values = block.get(key) or []
    return values[i] if i < len(values) else None


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    resp = await client.get(API, params=params(settings), timeout=15)
    resp.raise_for_status()
    return parse(resp.json(), settings)
