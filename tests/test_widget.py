import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.protocol import PROTOCOL_VERSION
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher

widget_mod = pytest.importorskip("framelab.transport.widget")


@pytest.fixture
def setup(monkeypatch):
    sent = []
    d = Dispatcher(Session([RootSpec("ventas", pd.DataFrame({"a": [1, 2]}), None)]))
    w = widget_mod.FramelabWidget(d)
    monkeypatch.setattr(w, "send", lambda content, buffers=None: sent.append((content, buffers)))
    return w, d, sent


def test_widget_answers_requests(setup):
    w, _, sent = setup
    msg = {"v": PROTOCOL_VERSION, "id": "c1", "type": "req", "method": "session.snapshot"}
    w._on_msg(w, msg, [])
    content, buffers = sent[-1]
    assert content["id"] == "c1"
    assert content["result"]["nodes"][0]["name"] == "ventas"
    assert buffers is None


def test_widget_receives_events(setup):
    _, d, sent = setup
    d.emit("test.event", {"x": 1}, [b"abc"])
    content, buffers = sent[-1]
    assert content["method"] == "test.event" and buffers == [b"abc"]


def test_bad_message_returns_error(setup):
    w, _, sent = setup
    w._on_msg(w, {"v": 999}, [])
    assert sent[-1][0]["error"]["code"] == "bad_request"


def test_close_detaches_from_dispatcher(setup):
    w, d, _ = setup
    assert d.client_count == 1
    w.close()
    assert d.client_count == 0


def test_height_trait(setup):
    w, _, _ = setup
    assert w.height == 720
