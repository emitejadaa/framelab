import pandas as pd
import pytest
from websockets.sync.client import connect

import framelab as fl
import framelab.api as api
from framelab.env import Env
from framelab.protocol import PROTOCOL_VERSION, decode_frame, encode_frame


@pytest.fixture
def ventas():
    return pd.DataFrame({"a": range(1000), "b": 0, "c": 0, "d": 0, "e": 0})


def fake_window(record):
    """Stand-in for the real window: behaves like the frontend over the real WebSocket."""

    def _open(server, *, title="framelab"):
        record["title"] = title
        url = f"ws://127.0.0.1:{server.port}/ws?token={server.token}"
        with connect(url, origin=f"http://127.0.0.1:{server.port}") as ws:
            hello = {
                "v": PROTOCOL_VERSION,
                "id": "1",
                "type": "req",
                "method": "session.hello",
                "params": {"protocol_version": PROTOCOL_VERSION, "client": "ws"},
            }
            ws.send(encode_frame(hello))
            record["hello"] = decode_frame(ws.recv(timeout=5))[0]["result"]
            snap = {"v": PROTOCOL_VERSION, "id": "2", "type": "req", "method": "session.snapshot"}
            ws.send(encode_frame(snap))
            record["snapshot"] = decode_frame(ws.recv(timeout=5))[0]["result"]
        return "fake"

    return _open


def test_explore_window_mode_serves_session_and_returns_it(monkeypatch, ventas, tmp_path):
    record = {}
    monkeypatch.setattr(api, "detect_env", lambda: Env.SCRIPT)
    monkeypatch.setattr(api, "_open_window", fake_window(record))
    monkeypatch.setattr(api, "_static_dir", lambda: tmp_path)
    session = fl.explore(ventas)
    assert session.names == ["ventas"]
    nodes = record["snapshot"]["nodes"]
    assert [(n["id"], n["name"], n["kind"], n["shape"]) for n in nodes] == [
        ("n1", "ventas", "DataFrame", [1000, 5])
    ]
    assert "ventas" in record["title"]
    assert fl.last_session() is session


def test_explore_requires_pandas(monkeypatch):
    monkeypatch.setattr(api, "_open_window", lambda *a, **k: "fake")
    with pytest.raises(TypeError, match="DataFrame or Series"):
        fl.explore([1, 2, 3], mode="window")


def test_explore_requires_something():
    with pytest.raises(TypeError, match="at least one"):
        fl.explore()


def test_explore_inline_mode_displays_widget(monkeypatch, ventas):
    shown = []
    monkeypatch.setattr(api, "detect_env", lambda: Env.JUPYTER)
    monkeypatch.setattr(api, "_display", shown.append)
    session = fl.explore(ventas)
    assert len(shown) == 1 and session.widget is shown[0]
    session.widget.close()


def test_window_request_from_notebook_falls_back_inline(monkeypatch, ventas):
    shown = []
    monkeypatch.setattr(api, "detect_env", lambda: Env.JUPYTER)
    monkeypatch.setattr(api, "_display", shown.append)
    with pytest.warns(UserWarning, match="inline"):
        session = fl.explore(ventas, mode="window")
    assert shown and session.widget is shown[0]
    session.widget.close()
