"""Current conditions, hourly strip, daily forecast, UV, air quality and moon phase (Open-Meteo, free, no key)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
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


NOWCAST_SLOTS = 48  # 12 hours of 15-minute slots
SNOW_CODES = {71, 73, 75, 77, 85, 86}


def rain_summary(times: list[str], precip: list[Any], codes: list[Any] | None, now: str, imperial: bool) -> dict[str, Any]:
    """What the next hours hold, from 15-minute precipitation slots (local "YYYY-MM-DDTHH:MM" strings).

    Returns {"kind": "starts"|"stops"|"later"|"ongoing"|"dry"|"", "at": time or None, "what": "rain"|"snow", "soon": bool}.
    The page turns it into "Rain starts around 4:15 PM". "soon" = within two hours (worth highlighting).
    """
    threshold = 0.01 if imperial else 0.25
    slot = now[:14] + f"{(int(now[14:16]) // 15) * 15:02d}" if len(now) >= 16 else now
    rows = [(t, p, (codes or [None] * len(times))[i] if i < len(codes or []) else None) for i, (t, p) in enumerate(zip(times, precip)) if t >= slot]
    if not rows:
        return {"kind": "", "at": None, "what": "rain", "soon": False}

    def wet(row):
        try:
            return float(row[1] or 0) >= threshold
        except (TypeError, ValueError):
            return False

    def what(row):
        try:
            return "snow" if int(row[2]) in SNOW_CODES else "rain"
        except (TypeError, ValueError):
            return "rain"

    if wet(rows[0]):
        for row in rows[1:]:
            if not wet(row):
                return {"kind": "stops", "at": row[0], "what": what(rows[0]), "soon": True}
        return {"kind": "ongoing", "at": None, "what": what(rows[0]), "soon": True}
    for i, row in enumerate(rows[1:], start=1):
        if wet(row):
            soon = i <= 8
            return {"kind": "starts" if soon else "later", "at": row[0], "what": what(row), "soon": soon}
    return {"kind": "dry", "at": None, "what": "rain", "soon": False}


def _naive(value: Any) -> datetime | None:
    try:
        return datetime.strptime(str(value)[:16], "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def sun_progress(sunrise: Any, sunset: Any, now: Any, next_sunrise: Any = None) -> dict[str, Any]:
    """Where the sun is in its day: progress 0..1 through daylight, or through the night after sunset."""
    sr, ss, t = _naive(sunrise), _naive(sunset), _naive(now)
    if not (sr and ss and t):
        return {"sunrise": sunrise, "sunset": sunset, "progress": 0.0, "is_day": True}
    if sr <= t < ss:
        return {"sunrise": sunrise, "sunset": sunset, "progress": round((t - sr) / (ss - sr), 3), "is_day": True}
    nxt = _naive(next_sunrise) or (sr + timedelta(days=1))
    if t < sr:  # before dawn: the night began at yesterday's sunset
        prev_ss = ss - timedelta(days=1)
        return {"sunrise": sunrise, "sunset": sunset, "progress": round(max(0.0, (t - prev_ss) / (sr - prev_ss)), 3), "is_day": False}
    return {"sunrise": sunrise, "sunset": sunset, "progress": round(min(1.0, (t - ss) / (nxt - ss)), 3), "is_day": False}


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
        "minutely_15": "precipitation,weather_code",  # 15-minute nowcast (HRRR in the US) for "rain starts at…"
        "forecast_minutely_15": NOWCAST_SLOTS,
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

    minutely_raw = raw.get("minutely_15") or {}
    now_local = cur.get("time") or ""
    rain = rain_summary(minutely_raw.get("time") or [], minutely_raw.get("precipitation") or [], minutely_raw.get("weather_code"), now_local, settings.imperial)
    nowcast = [
        {"time": t, "precip": _get(minutely_raw, "precipitation", i)}
        for i, t in enumerate(minutely_raw.get("time") or []) if t >= now_local[:14] + "00"
    ][:8]
    today = daily[0] if daily else {}
    sun = sun_progress(today.get("sunrise"), today.get("sunset"), now_local, daily[1].get("sunrise") if len(daily) > 1 else None)

    return {
        "location": settings.cfg["location"]["name"],
        "rain": rain,
        "nowcast": nowcast,
        "sun": sun,
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
