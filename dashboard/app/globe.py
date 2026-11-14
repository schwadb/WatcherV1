"""God's Eye View (github.com/bilawalsidhu/gods-eye-view): the 3D globe behind the ☰ → Globe button.

Three jobs live here:
- install/update it with deploy/globe.sh in the background and report progress to the phone page;
- keep it running as a user service (`npm run dev` on 127.0.0.1:4173), like ChronAlert and spotifyd;
- serve it to the TV's browser through the dashboard's own port under the name `globe.localhost`.

That last part is needed because the app refuses to be shown inside another page (it sends
`X-Frame-Options: DENY`), and its only framable mode hides every control. Browsers resolve any
`*.localhost` name to this computer, so the TV page can frame `http://globe.localhost:<port>/`;
the proxy forwards those requests to the app with the two framing headers removed. Only
connections from this computer are forwarded, so the app stays as private as it is on its own.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .config import ROOT
from .userservice import UserService, home

SERVICE_NAME = "globe"
GLOBE_HOST = "globe.localhost"
DEFAULT_PORT = 4173
SCRIPT = ROOT / "deploy" / "globe.sh"
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


# ---------------------------------------------------------------------------------------------
# where things are
# ---------------------------------------------------------------------------------------------
def install_dir(h: Path | None = None) -> Path:
    return Path(os.environ.get("GLOBE_DIR") or (home(h) / "Applications" / "gods-eye-view"))


def private_node_dir(h: Path | None = None) -> Path:
    return Path(os.environ.get("GLOBE_NODE_DIR") or (home(h) / ".local" / "share" / "watcher-dashboard" / "node"))


def _node_major(node: str) -> int:
    try:
        out = subprocess.run([node, "-v"], capture_output=True, text=True, timeout=10).stdout.strip()
        return int(out.lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0


def node_bin(h: Path | None = None, system_node: str | None = None, system_major: int | None = None) -> str:
    """The folder holding the node/npm the globe runs with: the private Node 24 if downloaded, else a system Node 24/26."""
    private = private_node_dir(h) / "bin"
    if (private / "node").exists():
        return str(private)
    sys_node = system_node if system_node is not None else shutil.which("node")
    if sys_node:
        major = system_major if system_major is not None else _node_major(sys_node)
        if major in (24, 26):
            return str(Path(sys_node).resolve().parent)
    return ""


def installed(h: Path | None = None) -> bool:
    d = install_dir(h)
    return (d / "package.json").is_file() and (d / "node_modules").is_dir()


# ---------------------------------------------------------------------------------------------
# user service
# ---------------------------------------------------------------------------------------------
def service(h: Path | None = None, port: int = DEFAULT_PORT, bin_dir: str | None = None) -> UserService:
    d = install_dir(h)
    bin_dir = bin_dir if bin_dir is not None else node_bin(h)
    path = f"{bin_dir}:/usr/local/bin:/usr/bin:/bin" if bin_dir else "/usr/local/bin:/usr/bin:/bin"
    extra = f"WorkingDirectory={d}\nEnvironment=PATH={path}\nEnvironment=PORT={port}\nEnvironment=HOST=127.0.0.1\n"
    npm = f"{bin_dir}/npm" if bin_dir else "/usr/bin/npm"
    return UserService(SERVICE_NAME, "God's Eye View globe", f"{npm} run dev", extra, h)


def service_text(h: Path | None = None, port: int = DEFAULT_PORT, bin_dir: str | None = None) -> str:
    return service(h, port, bin_dir).text()


def start(h: Path | None = None, port: int = DEFAULT_PORT) -> str:
    """Write the user service, enable it and start it now. Returns a message for the page."""
    if not installed(h):
        raise ValueError("God's Eye View is not installed yet. Press Install first (or run: bash deploy/globe.sh install).")
    if not node_bin(h):
        raise ValueError("No Node.js 24 was found. Press Install again; it downloads a private copy.")
    service(h, port).install()
    return "The globe is now started by the computer and restarted if it stops."


def remove(h: Path | None = None) -> str:
    service(h, DEFAULT_PORT, "").remove()
    return "The globe is no longer started by the dashboard."


def status(h: Path | None = None) -> dict:
    return service(h, DEFAULT_PORT, "").status()


# ---------------------------------------------------------------------------------------------
# background installer (deploy/globe.sh install)
# ---------------------------------------------------------------------------------------------
class Installer:
    """Runs the install script once at a time and keeps its last lines for the phone page."""

    def __init__(self, mock: bool = False):
        self.mock = mock
        self.lines: deque[str] = deque(maxlen=60)
        self.task: asyncio.Task | None = None
        self.started = 0.0
        self.finished = 0.0
        self.exit_code: int | None = None
        self.on_done = None  # async callback(exit_code)

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def summary(self) -> dict[str, Any]:
        return {"running": self.running, "exit_code": self.exit_code, "started": self.started, "finished": self.finished, "log": list(self.lines)}

    def begin(self) -> None:
        if self.running:
            raise RuntimeError("an install is already running")
        self.lines.clear()
        self.exit_code = None
        self.started, self.finished = time.time(), 0.0
        self.task = asyncio.create_task(self._run(), name="globe-install")

    async def _run(self) -> None:
        code = 1
        try:
            if self.mock:
                for line in ("[globe] downloading God's Eye View (mock)", "[globe] installing the app's packages (mock)", "[globe] done."):
                    self.lines.append(line)
                    await asyncio.sleep(1)
                code = 0
            else:
                proc = await asyncio.create_subprocess_exec(
                    "bash", str(SCRIPT), "install", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                    env={**os.environ, "HOME": str(home())},
                )
                assert proc.stdout is not None
                async for raw in proc.stdout:
                    self.lines.append(raw.decode("utf-8", "replace").rstrip())
                code = await proc.wait()
        except Exception as exc:  # noqa: BLE001 - show the reason on the page
            self.lines.append(f"install failed: {exc}")
            code = 1
        finally:
            self.exit_code = code
            self.finished = time.time()
        if self.on_done is not None:
            try:
                await self.on_done(code)
            except Exception as exc:  # noqa: BLE001
                self.lines.append(f"after install: {exc}")


def script_status() -> dict[str, Any]:
    """What deploy/globe.sh sees (dir, installed, node); never raises."""
    try:
        out = subprocess.run(["bash", str(SCRIPT), "status"], capture_output=True, text=True, timeout=20, env={**os.environ, "HOME": str(home())}).stdout
        return json.loads(out.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return {"dir": str(install_dir()), "installed": installed(), "node": node_bin(), "node_version": ""}


# ---------------------------------------------------------------------------------------------
# header rewriting (pure, unit-tested)
# ---------------------------------------------------------------------------------------------
def strip_framing(headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Response headers minus X-Frame-Options, and minus the frame-ancestors rule of a CSP (the rest of it stays)."""
    out: list[tuple[str, str]] = []
    for name, value in headers:
        key = name.lower()
        if key in HOP_BY_HOP - {"content-length"} or key == "x-frame-options":
            continue
        if key == "content-security-policy":
            kept = [d.strip() for d in value.split(";") if d.strip() and not d.strip().lower().startswith("frame-ancestors")]
            if not kept:
                continue
            value = "; ".join(kept)
        out.append((name, value))
    return out


def upstream_headers(headers: list[tuple[str, str]], upstream: str) -> list[tuple[str, str]]:
    """Request headers for the app: Host/Origin/Referer point at the app itself, hop-by-hop ones go, nothing is added."""
    out: list[tuple[str, str]] = []
    for name, value in headers:
        key = name.lower()
        if key in HOP_BY_HOP or key.startswith("x-forwarded-") or key in ("forwarded", "via"):
            continue
        if key == "origin" and GLOBE_HOST in value:
            value = f"http://{upstream}"
        elif key == "referer" and GLOBE_HOST in value:
            value = f"http://{upstream}/"
        out.append((name, value))
    out.append(("host", upstream))
    return out


def is_globe_host(host: str) -> bool:
    return host.split(":")[0].lower() == GLOBE_HOST


DOWN_PAGE = """<!doctype html><meta charset="utf-8"><title>Globe not running</title>
<body style="margin:0;background:#0b0f14;color:#e6edf3;font:22px system-ui;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center">
<div><p style="font-size:3rem;margin:0">&#128752;</p><p>God's Eye View isn't running on the dashboard computer.</p>
<p style="opacity:.75">On the phone's settings page, under <b>God's Eye View globe</b>, press <b>Install</b> (first time) or <b>Start the globe with the dashboard</b>.</p></div></body>"""


class GlobeProxy:
    """ASGI middleware: requests for globe.localhost from this computer go to the app; everything else passes through."""

    def __init__(self, app, client_getter, port_getter):
        self.app = app
        self.client_getter = client_getter  # () -> httpx.AsyncClient
        self.port_getter = port_getter  # () -> int

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in scope.get("headers", [])]
        host = next((v for k, v in headers if k.lower() == "host"), "")
        if not is_globe_host(host):
            return await self.app(scope, receive, send)
        client = scope.get("client") or ("", 0)
        if client[0] not in LOOPBACK:
            return await self._refuse(scope, send, 403, "The globe is only shown on the dashboard computer itself.")
        if scope["type"] == "websocket":  # Vite's hot-reload socket; the page works without it
            await receive()
            return await send({"type": "websocket.close", "code": 1008})
        if any(k.lower() == "upgrade" and v.lower() == "websocket" for k, v in headers):  # same, on a server without websocket support
            return await self._refuse(scope, send, 404, "The globe's hot-reload socket is not passed through; the page works without it.")
        await self._proxy(scope, receive, send, headers)

    async def _refuse(self, scope, send, status: int, text: str):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        body = text.encode()
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def _proxy(self, scope, receive, send, headers):
        upstream = f"127.0.0.1:{self.port_getter()}"
        raw = scope.get("raw_path") or quote(scope["path"], safe="/%:@!$&'()*+,;=~-._").encode("latin-1")
        url = f"http://{upstream}{raw.decode('latin-1')}"
        if scope.get("query_string"):
            url += "?" + scope["query_string"].decode("latin-1")

        async def body():
            while True:
                msg = await receive()
                if msg["type"] != "http.request":
                    break
                if msg.get("body"):
                    yield msg["body"]
                if not msg.get("more_body"):
                    break

        req_headers = upstream_headers(headers, upstream)
        method = scope["method"]
        content = body() if method not in ("GET", "HEAD", "OPTIONS") else None
        client: httpx.AsyncClient = self.client_getter()
        try:
            req = client.build_request(method, url, headers=req_headers, content=content, timeout=httpx.Timeout(10, read=120))
            resp = await client.send(req, stream=True)
        except httpx.HTTPError:
            page = DOWN_PAGE.encode()
            await send({"type": "http.response.start", "status": 502, "headers": [(b"content-type", b"text/html; charset=utf-8"), (b"content-length", str(len(page)).encode()), (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": page})
            return
        try:
            out = strip_framing(list(resp.headers.multi_items()))
            await send({"type": "http.response.start", "status": resp.status_code, "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in out]})
            async for chunk in resp.aiter_raw():
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            await resp.aclose()
