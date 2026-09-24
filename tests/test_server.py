import json
import os
import stat
import sys
import time

import httpx
import pandas as pd
import pytest
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

from framelab.naming import RootSpec
from framelab.protocol import PROTOCOL_VERSION, decode_frame, encode_frame
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher, Reply
from framelab.transport.server import COOKIE, FramelabServer


@pytest.fixture
def static_dir(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "framelab.js").write_text("export function mountWs() {}", encoding="utf-8")
    (static / "framelab.css").write_text(".fl-root{}", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    return static


@pytest.fixture
def server(static_dir):
    d = Dispatcher(Session([RootSpec("ventas", pd.DataFrame({"a": range(3)}), None)]))
    d.register("echo", lambda params, bufs: Reply(params, bufs))
    srv = FramelabServer(d, static_dir)
    srv.start()
    yield srv
    srv.stop()


def ws_url(srv, token=None):
    url = f"ws://127.0.0.1:{srv.port}/ws"
    return url + (f"?token={token}" if token else "")


def origin(srv):
    return f"http://127.0.0.1:{srv.port}"


def hello():
    return {
        "v": PROTOCOL_VERSION,
        "id": "h",
        "type": "req",
        "method": "session.hello",
        "params": {"protocol_version": PROTOCOL_VERSION, "client": "ws"},
    }


def test_binds_loopback_random_port(server):
    assert server.port > 0
    assert server.url == f"http://127.0.0.1:{server.port}/"


def test_index_requires_token(server):
    assert httpx.get(server.url).status_code == 403
    assert httpx.get(server.url + "?token=wrong").status_code == 403


def test_token_login_serves_index_sets_cookie_and_strips_token(server):
    # No redirect: a 303 after a navigation started from the file:// redirect page is
    # cross-site, so a SameSite=Strict cookie would not be sent on the second hop.
    with httpx.Client() as client:
        r = client.get(server.login_url)
        assert r.status_code == 200 and "framelab.js" in r.text
        assert "history.replaceState" in r.text
        set_cookie = r.headers["set-cookie"].lower()
        assert "httponly" in set_cookie and "samesite=strict" in set_cookie
        assert r.headers["cache-control"] == "no-store"
        r2 = client.get(server.url)
        assert r2.status_code == 200 and "framelab.js" in r2.text


def test_static_requires_auth_and_blocks_traversal(server):
    assert httpx.get(server.url + "static/framelab.js").status_code == 403
    cookies = {COOKIE: server.token}
    assert httpx.get(server.url + "static/framelab.js", cookies=cookies).status_code == 200
    assert httpx.get(server.url + "static/..%2Fsecret.txt", cookies=cookies).status_code == 404
    assert httpx.get(server.url + "static/missing.js", cookies=cookies).status_code == 404


def test_rejects_foreign_host_header(server):
    assert httpx.get(server.login_url, headers={"Host": "evil.example"}).status_code == 403
    r = httpx.get(
        server.url + "static/framelab.js",
        headers={"Host": "evil.example"},
        cookies={COOKIE: server.token},
    )
    assert r.status_code == 403


def test_ws_requires_token_and_same_origin(server):
    cookie = {"Cookie": f"{COOKIE}={server.token}"}
    with pytest.raises(InvalidStatus):
        connect(ws_url(server), origin=origin(server))
    with pytest.raises(InvalidStatus):
        connect(ws_url(server), origin="http://evil.example", additional_headers=cookie)
    with pytest.raises(InvalidStatus):
        connect(ws_url(server), additional_headers=cookie)
    with connect(ws_url(server), origin=origin(server), additional_headers=cookie) as ws:
        ws.send(encode_frame(hello()))
        env, _ = decode_frame(ws.recv(timeout=5))
        assert env["result"]["protocol_version"] == PROTOCOL_VERSION
    assert server.ever_connected.is_set()


def test_ws_binary_roundtrip_and_events(server):
    with connect(ws_url(server, server.token), origin=origin(server)) as ws:
        request = {"v": PROTOCOL_VERSION, "id": "e", "type": "req", "method": "echo"}
        ws.send(encode_frame({**request, "params": {"x": 1}}, [b"abc"]))
        env, bufs = decode_frame(ws.recv(timeout=5))
        assert env["result"] == {"x": 1} and bufs == [b"abc"]
        server.dispatcher.emit("test.event", {"n": 1})
        env, _ = decode_frame(ws.recv(timeout=5))
        assert env["type"] == "evt" and env["method"] == "test.event"


def test_bad_frame_gets_error_not_disconnect(server):
    with connect(ws_url(server, server.token), origin=origin(server)) as ws:
        ws.send("garbage")
        env, _ = decode_frame(ws.recv(timeout=5))
        assert env["error"]["code"] == "bad_request"
        ws.send(encode_frame(hello()))
        env, _ = decode_frame(ws.recv(timeout=5))
        assert "result" in env


def test_idle_tracking(server):
    assert server.client_count == 0
    with connect(ws_url(server, server.token), origin=origin(server)) as ws:
        ws.send(encode_frame(hello()))
        ws.recv(timeout=5)
        assert server.client_count == 1 and server.idle_for() == 0.0
    deadline = time.monotonic() + 5
    while server.client_count and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.client_count == 0 and server.idle_for() >= 0.0


def test_redirect_file_is_private_and_points_to_login(server):
    path = server.write_redirect_file()
    try:
        assert json.dumps(server.login_url) in path.read_text(encoding="utf-8")
        if sys.platform != "win32":
            assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    finally:
        path.unlink()


def test_stop_releases_port(static_dir):
    d = Dispatcher(Session([RootSpec("v", pd.DataFrame({"a": [1]}), None)]))
    srv = FramelabServer(d, static_dir)
    srv.start()
    port = srv.port
    srv.stop()
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"http://127.0.0.1:{port}/", timeout=1)
