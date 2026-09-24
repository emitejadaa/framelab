import pandas as pd

from framelab import __version__
from framelab.naming import RootSpec
from framelab.protocol import PROTOCOL_VERSION
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher, Reply


def dispatcher():
    return Dispatcher(Session([RootSpec("ventas", pd.DataFrame({"a": [1]}), None)]))


def req(method, params=None, msg_id="c1"):
    env = {"v": PROTOCOL_VERSION, "id": msg_id, "type": "req", "method": method}
    if params is not None:
        env["params"] = params
    return env


def test_hello_ok():
    d = dispatcher()
    params = {"protocol_version": PROTOCOL_VERSION, "client": "ws"}
    env, bufs = d.handle(req("session.hello", params), [])
    assert env["result"] == {
        "protocol_version": PROTOCOL_VERSION,
        "framelab_version": __version__,
        "session_id": d.session.id,
    }
    assert bufs == []


def test_hello_mismatch():
    params = {"protocol_version": 999, "client": "ws"}
    env, _ = dispatcher().handle(req("session.hello", params), [])
    assert env["error"]["code"] == "protocol_mismatch"


def test_snapshot():
    env, _ = dispatcher().handle(req("session.snapshot"), [])
    assert env["result"]["roots"][0]["name"] == "ventas"


def test_unknown_method():
    env, _ = dispatcher().handle(req("nope.nope"), [])
    assert env["error"]["code"] == "unknown_method"
    assert env["id"] == "c1"


def test_duplicate_registration_rejected():
    d = dispatcher()
    try:
        d.register("app.ping", lambda p, b: None)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_handler_exception_becomes_internal_error_with_traceback():
    d = dispatcher()
    d.register("boom", lambda params, bufs: 1 / 0)
    env, _ = d.handle(req("boom"), [])
    assert env["error"]["code"] == "internal"
    assert "ZeroDivisionError" in env["error"]["message"]
    assert "Traceback" in env["error"]["traceback"]


def test_reply_with_buffers():
    d = dispatcher()
    d.register("echo", lambda params, bufs: Reply({"n": len(bufs)}, [b"x" + b for b in bufs]))
    env, bufs = d.handle(req("echo"), [b"1", b"2"])
    assert env["result"] == {"n": 2}
    assert bufs == [b"x1", b"x2"]


def test_cancel_is_ignored_and_non_requests_rejected():
    d = dispatcher()
    assert d.handle({"v": PROTOCOL_VERSION, "id": "c1", "type": "cancel"}, []) is None
    env, _ = d.handle({"v": PROTOCOL_VERSION, "id": "c1", "type": "res"}, [])
    assert env["error"]["code"] == "bad_request"


def test_emit_reaches_clients_until_removed():
    d = dispatcher()
    got = []
    remove = d.add_client(lambda env, bufs: got.append((env["method"], bufs)))
    assert d.client_count == 1
    d.emit("x.changed", {"a": 1}, [b"z"])
    remove()
    d.emit("x.changed", {"a": 2})
    assert got == [("x.changed", [b"z"])]
    assert d.client_count == 0


def test_emit_survives_a_failing_client():
    d = dispatcher()
    got = []

    def dead(env, bufs):
        raise RuntimeError("dead")

    d.add_client(dead)
    d.add_client(lambda env, bufs: got.append(env["method"]))
    d.emit("ping")
    assert got == ["ping"]
