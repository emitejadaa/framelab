"""Local HTTP + WebSocket server for window mode (127.0.0.1 only, token protected)."""

from __future__ import annotations

import asyncio
import html
import json
import os
import secrets
import tempfile
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection, Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from ..protocol import ProtocolError, decode_frame, encode_frame, make_error
from .dispatcher import Dispatcher

__all__ = ["COOKIE", "FramelabServer"]

COOKIE = "framelab_token"

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
html,body,#app{{height:100%;margin:0}}
body{{background:#fafafa}}
@media (prefers-color-scheme:dark){{body{{background:#18181b}}}}
.fl-boot{{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
font:13px system-ui,-apple-system,"Segoe UI",sans-serif;color:#71717a;gap:8px}}
.fl-boot i{{width:14px;height:14px;border:2px solid #d4d4d8;border-top-color:#3b82f6;
border-radius:50%;animation:fl-boot-spin .8s linear infinite}}
@keyframes fl-boot-spin{{to{{transform:rotate(360deg)}}}}
</style>
<link rel="stylesheet" href="/static/framelab.css">
</head>
<body>
<div id="app"><div class="fl-boot"><i></i><span>framelab</span></div></div>
<script type="module">
import {{ mountWs }} from "/static/framelab.js";
const el = document.getElementById("app");
el.replaceChildren();
mountWs(el, (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
</script>
</body>
</html>
"""


class FramelabServer:
    """Serves the bundle and one WebSocket endpoint bound to a Dispatcher.

    Security model: loopback only, random port, a 32-byte token that never appears on a
    command line (the launcher hands the browser a private redirect file), an HttpOnly
    SameSite=Strict cookie afterwards, strict Host checks (DNS rebinding) and strict
    Origin checks on the WebSocket (cross-site WebSocket hijacking). No CORS.
    """

    def __init__(
        self,
        dispatcher: Dispatcher,
        static_dir: Path | str,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
        title: str = "framelab",
        extra_origins: Iterable[str] = (),
        extra_hosts: Iterable[str] = (),
    ) -> None:
        self.dispatcher = dispatcher
        self.static_dir = Path(static_dir).resolve()
        self.host = host
        self._port = port
        self.token = token or secrets.token_urlsafe(32)
        self.title = title
        self._extra_origins = frozenset(extra_origins)
        self._extra_hosts = frozenset(extra_hosts)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._clients = 0
        self._clients_lock = threading.Lock()
        self._last_disconnect = time.monotonic()
        self.ever_connected = threading.Event()
        self.app = Starlette(
            routes=[
                Route("/", self._index),
                Route("/static/{path:path}", self._static),
                WebSocketRoute("/ws", self._ws),
            ]
        )

    # ---- lifecycle -------------------------------------------------------------------
    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}/"

    @property
    def login_url(self) -> str:
        return f"{self.url}?token={self.token}"

    def start(self, timeout: float = 10.0) -> None:
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self._port,
            log_level="warning",
            lifespan="off",
            ws="websockets-sansio",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, name="framelab-server", daemon=True
        )
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive():
                raise RuntimeError("framelab's local server failed to start")
            if time.monotonic() > deadline:
                raise TimeoutError("framelab's local server did not start in time")
            time.sleep(0.01)
        self._port = self._server.servers[0].sockets[0].getsockname()[1]

    def stop(self, timeout: float = 5.0) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout)

    # ---- client tracking -------------------------------------------------------------
    @property
    def client_count(self) -> int:
        with self._clients_lock:
            return self._clients

    def idle_for(self) -> float:
        """Seconds since the last client left (0 while any client is connected)."""
        with self._clients_lock:
            return 0.0 if self._clients else time.monotonic() - self._last_disconnect

    def _joined(self) -> None:
        with self._clients_lock:
            self._clients += 1
        self.ever_connected.set()

    def _left(self) -> None:
        with self._clients_lock:
            self._clients -= 1
            self._last_disconnect = time.monotonic()

    def write_redirect_file(self) -> Path:
        """A private (0600) HTML file that forwards the browser to the login URL."""
        fd, name = tempfile.mkstemp(prefix="framelab-", suffix=".html")
        content = (
            '<!doctype html><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0;url={html.escape(self.login_url)}">'
            f"<script>location.replace({json.dumps(self.login_url)})</script>"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(name, 0o600)
        return Path(name)

    # ---- security --------------------------------------------------------------------
    def _host_ok(self, conn: HTTPConnection) -> bool:
        allowed = {f"127.0.0.1:{self._port}", f"localhost:{self._port}"} | self._extra_hosts
        return conn.headers.get("host") in allowed

    def _origin_ok(self, conn: HTTPConnection) -> bool:
        allowed = {f"http://127.0.0.1:{self._port}", f"http://localhost:{self._port}"}
        return conn.headers.get("origin") in allowed | self._extra_origins

    def _token_matches(self, value: str | None) -> bool:
        return value is not None and secrets.compare_digest(value, self.token)

    def _authed(self, conn: HTTPConnection) -> bool:
        return self._token_matches(conn.cookies.get(COOKIE)) or self._token_matches(
            conn.query_params.get("token")
        )

    # ---- routes ----------------------------------------------------------------------
    async def _index(self, request: Request) -> Response:
        if not self._host_ok(request):
            return PlainTextResponse("forbidden", status_code=403)
        query_token = request.query_params.get("token")
        if query_token is not None:
            if not self._token_matches(query_token):
                return PlainTextResponse("forbidden", status_code=403)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(COOKIE, self.token, httponly=True, samesite="strict", path="/")
            return response
        if not self._token_matches(request.cookies.get(COOKIE)):
            return PlainTextResponse("forbidden", status_code=403)
        return HTMLResponse(
            INDEX_TEMPLATE.format(title=html.escape(self.title)),
            headers={"Cache-Control": "no-store"},
        )

    async def _static(self, request: Request) -> Response:
        if not (self._host_ok(request) and self._authed(request)):
            return PlainTextResponse("forbidden", status_code=403)
        target = (self.static_dir / request.path_params["path"]).resolve()
        if not target.is_relative_to(self.static_dir) or not target.is_file():
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(target, headers={"Cache-Control": "no-store"})

    async def _ws(self, ws: WebSocket) -> None:
        if not (self._host_ok(ws) and self._origin_ok(ws) and self._authed(ws)):
            await ws.close(code=4403)
            return
        await ws.accept()
        loop = asyncio.get_running_loop()
        send_lock = asyncio.Lock()

        async def send_frame(frame: bytes | str) -> None:
            async with send_lock:
                if isinstance(frame, bytes):
                    await ws.send_bytes(frame)
                else:
                    await ws.send_text(frame)

        def send_from_any_thread(env: Any, buffers: list[bytes]) -> None:
            asyncio.run_coroutine_threadsafe(send_frame(encode_frame(env, buffers)), loop)

        remove = self.dispatcher.add_client(send_from_any_thread)
        self._joined()
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if data is None:
                    data = message.get("text", "")
                try:
                    env, buffers = decode_frame(data)
                except ProtocolError as exc:
                    await send_frame(encode_frame(make_error("", "bad_request", str(exc))))
                    continue
                reply = await run_in_threadpool(self.dispatcher.handle, env, buffers)
                if reply is not None:
                    await send_frame(encode_frame(*reply))
        finally:
            remove()
            self._left()
