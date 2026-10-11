"""Spotify "now playing" via the Web API, authorized once with PKCE (client ID only, no secret)."""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from ..config import Settings
from ..store import JsonStore

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
NOW_PLAYING_URL = "https://api.spotify.com/v1/me/player/currently-playing"
SCOPES = "user-read-currently-playing user-read-playback-state user-modify-playback-state playlist-read-private playlist-read-collaborative user-library-read"
CONTROL_SCOPE = "user-modify-playback-state"
API = "https://api.spotify.com/v1"
# Spotify only allows http:// redirect URIs on the loopback address; LAN addresses must be https.
REDIRECT_PATH = "/api/spotify/callback"


def redirect_uri(settings: Settings) -> str:
    return f"http://127.0.0.1:{settings.cfg['server']['port']}{REDIRECT_PATH}"


def token_store(settings: Settings) -> JsonStore:
    return JsonStore(settings.data_dir / "spotify.json", {})


def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def auth_url(settings: Settings, challenge: str, state: str) -> str:
    params = {
        "client_id": settings.spotify_client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri(settings),
        "scope": SCOPES,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def parse_pasted_url(text: str) -> tuple[str, str]:
    """From the address bar after Spotify redirects: returns (code, state)."""
    text = text.strip()
    query = urlparse(text).query if "?" in text else text
    q = parse_qs(query)
    code = (q.get("code") or [""])[0]
    state = (q.get("state") or [""])[0]
    if not code:
        if q.get("error"):
            raise ValueError(f"Spotify said: {q['error'][0]}")
        raise ValueError("that address has no code in it; copy the whole address from the browser's address bar")
    return code, state


async def exchange_code(client: httpx.AsyncClient, settings: Settings, code: str, verifier: str) -> dict[str, Any]:
    resp = await client.post(
        TOKEN_URL,
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(settings), "client_id": settings.spotify_client_id, "code_verifier": verifier},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Spotify refused the sign-in ({resp.status_code}): {resp.text[:200]}")
    tok = resp.json()
    data = {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"), "expires_at": time.time() + int(tok.get("expires_in", 3600)), "scope": tok.get("scope", "")}
    token_store(settings).write(data)
    return data


async def _access_token(client: httpx.AsyncClient, settings: Settings) -> str:
    store = token_store(settings)
    tok = store.read()
    if not tok.get("refresh_token"):
        raise RuntimeError("Spotify is not connected yet (Music tab on the settings page)")
    if tok.get("expires_at", 0) - 60 > time.time() and tok.get("access_token"):
        return tok["access_token"]
    resp = await client.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": settings.spotify_client_id},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Spotify token refresh failed ({resp.status_code}); reconnect on the Music tab")
    new = resp.json()
    tok["access_token"] = new["access_token"]
    tok["expires_at"] = time.time() + int(new.get("expires_in", 3600))
    if new.get("refresh_token"):
        tok["refresh_token"] = new["refresh_token"]
    store.write(tok)
    return tok["access_token"]


def parse_now_playing(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw or not raw.get("item"):
        return {"playing": False, "provider": "spotify"}
    item = raw["item"]
    kind = raw.get("currently_playing_type", "track")
    if kind == "episode":
        artist = (item.get("show") or {}).get("name", "")
        images = (item.get("images") or []) or ((item.get("show") or {}).get("images") or [])
    else:
        artist = ", ".join(a.get("name", "") for a in item.get("artists") or [])
        images = (item.get("album") or {}).get("images") or []
    art = images[1]["url"] if len(images) > 1 else (images[0]["url"] if images else None)
    progress = int(raw.get("progress_ms") or 0)
    duration = int(item.get("duration_ms") or 0)
    return {
        "playing": bool(raw.get("is_playing")),
        "provider": "spotify",
        "title": item.get("name", ""),
        "artist": artist,
        "album": (item.get("album") or {}).get("name", ""),
        "art_url": art,
        "device": (raw.get("device") or {}).get("name", ""),
        "progress_ms": progress,
        "duration_ms": duration,
        "progress_pct": round(progress / duration * 100, 1) if duration else 0,
    }


async def fetch(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    if not settings.spotify_client_id:
        raise RuntimeError("SPOTIFY_CLIENT_ID is not set (Music tab on the settings page)")
    token = await _access_token(client, settings)
    resp = await client.get(NOW_PLAYING_URL, params={"additional_types": "track,episode"}, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    if resp.status_code == 204:
        return {"playing": False, "provider": "spotify"}
    if resp.status_code == 401:
        raise RuntimeError("Spotify rejected the token; reconnect on the Music tab")
    if resp.status_code == 429:
        raise RuntimeError("Spotify rate limit; slowing down")
    resp.raise_for_status()
    return parse_now_playing(resp.json())


def interval_seconds(settings: Settings, cache: Any) -> float:
    data = getattr(cache, "data", None) or {}
    base = float((settings.cfg.get("now_playing") or {}).get("refresh_seconds", 10))
    return base if data.get("playing") else max(base, 60.0)


# ---- playback control and the user's library (needs the newer scopes; reconnect once) --------
def can_control(settings: Settings) -> bool:
    """True when the stored token was granted with the playback-control permission."""
    tok = token_store(settings).read()
    return bool(tok.get("refresh_token")) and CONTROL_SCOPE in str(tok.get("scope", "")).split()


class SpotifyError(RuntimeError):
    pass


async def _call(client: httpx.AsyncClient, settings: Settings, method: str, path: str, **kw: Any) -> Any:
    token = await _access_token(client, settings)
    resp = await client.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=15, **kw)
    if resp.status_code in (200, 201):
        return resp.json() if resp.content else {}
    if resp.status_code in (202, 204):
        return {}
    if resp.status_code == 401:
        raise SpotifyError("Spotify rejected the token; reconnect on the Music tab")
    if resp.status_code == 403:
        detail = ""
        try:
            detail = (resp.json().get("error") or {}).get("message", "")
        except ValueError:
            pass
        if "scope" in detail.lower() or "permission" in detail.lower():
            raise SpotifyError("Spotify needs a new permission: press Reconnect on the Music tab")
        raise SpotifyError(detail or "Spotify refused (Premium is required to control playback)")
    if resp.status_code == 404:
        raise SpotifyError("no active player: the Dashboard device is not paired yet, or is not running")
    if resp.status_code == 429:
        raise SpotifyError("Spotify rate limit; try again in a moment")
    raise SpotifyError(f"Spotify error {resp.status_code}: {resp.text[:120]}")


async def devices(client: httpx.AsyncClient, settings: Settings) -> list[dict[str, Any]]:
    data = await _call(client, settings, "GET", "/me/player/devices")
    return [{"id": d.get("id"), "name": d.get("name", ""), "type": d.get("type", ""), "active": bool(d.get("is_active")), "volume": d.get("volume_percent")} for d in data.get("devices") or []]


def find_device(devs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    want = name.strip().lower()
    return next((d for d in devs if d["name"].strip().lower() == want), None)


async def play(client: httpx.AsyncClient, settings: Settings, device_id: str | None, context_uri: str | None = None, uris: list[str] | None = None) -> None:
    body: dict[str, Any] = {}
    if context_uri:
        body["context_uri"] = context_uri
    if uris:
        body["uris"] = uris
    params = {"device_id": device_id} if device_id else None
    await _call(client, settings, "PUT", "/me/player/play", params=params, json=body or None)


async def pause(client: httpx.AsyncClient, settings: Settings) -> None:
    await _call(client, settings, "PUT", "/me/player/pause")


async def skip(client: httpx.AsyncClient, settings: Settings, direction: str) -> None:
    await _call(client, settings, "POST", "/me/player/next" if direction == "next" else "/me/player/previous")


async def set_volume(client: httpx.AsyncClient, settings: Settings, pct: int, device_id: str | None = None) -> None:
    params: dict[str, Any] = {"volume_percent": max(0, min(100, int(pct)))}
    if device_id:
        params["device_id"] = device_id
    await _call(client, settings, "PUT", "/me/player/volume", params=params)


async def shuffle(client: httpx.AsyncClient, settings: Settings, on: bool) -> None:
    await _call(client, settings, "PUT", "/me/player/shuffle", params={"state": "true" if on else "false"})


async def transfer(client: httpx.AsyncClient, settings: Settings, device_id: str, play_now: bool = True) -> None:
    await _call(client, settings, "PUT", "/me/player", json={"device_ids": [device_id], "play": play_now})


def _art(images: list[dict[str, Any]] | None) -> str | None:
    images = images or []
    if not images:
        return None
    mid = sorted(images, key=lambda i: abs((i.get("width") or 300) - 300))
    return mid[0].get("url")


async def playlists(client: httpx.AsyncClient, settings: Settings) -> list[dict[str, Any]]:
    data = await _call(client, settings, "GET", "/me/playlists", params={"limit": 50})
    return [{"uri": p.get("uri"), "name": p.get("name", ""), "art": _art(p.get("images")), "by": (p.get("owner") or {}).get("display_name", ""), "tracks": (p.get("tracks") or {}).get("total")} for p in data.get("items") or [] if p]


async def albums(client: httpx.AsyncClient, settings: Settings) -> list[dict[str, Any]]:
    data = await _call(client, settings, "GET", "/me/albums", params={"limit": 50})
    out = []
    for item in data.get("items") or []:
        a = item.get("album") or {}
        out.append({"uri": a.get("uri"), "name": a.get("name", ""), "art": _art(a.get("images")), "by": ", ".join(x.get("name", "") for x in a.get("artists") or [])})
    return out


async def liked_songs_uris(client: httpx.AsyncClient, settings: Settings) -> list[str]:
    data = await _call(client, settings, "GET", "/me/tracks", params={"limit": 50})
    return [t["track"]["uri"] for t in data.get("items") or [] if t.get("track") and t["track"].get("uri")]
