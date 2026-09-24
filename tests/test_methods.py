import time

import pandas as pd
import pyarrow as pa
import pytest

from framelab.naming import RootSpec
from framelab.ops import op_to_json
from framelab.ops.build import call
from framelab.protocol import PROTOCOL_VERSION
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher


@pytest.fixture
def d():
    s = Session([RootSpec("ventas", pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}))])
    yield Dispatcher(s)
    s.close()


def req(method, params, msg_id="c1"):
    return {"v": PROTOCOL_VERSION, "id": msg_id, "type": "req", "method": method, "params": params}


def result(d, method, params):
    env, bufs = d.handle(req(method, params), [])
    assert "error" not in env, env.get("error")
    return env["result"], bufs


def test_apply_summary_window_code(d):
    events = []
    d.add_client(lambda env, bufs: events.append((env["method"], env["params"]["state"])))
    res, _ = result(d, "node.apply", {"op": op_to_json(call("n1", "head", n=2))})
    node = res["node"]
    assert node["name"] == "ventas_head" and node["state"] == "pending"
    summary, _ = result(d, "node.summary", {"id": node["id"]})
    assert summary["shape"] == [2, 2]
    meta, bufs = result(d, "node.window", {"id": node["id"], "offset": 0, "limit": 10})
    assert meta["nrows_total"] == 2 and pa.ipc.open_stream(bufs[0]).read_all().num_rows == 2
    code, _ = result(d, "node.code", {"id": node["id"], "mode": "step"})
    assert code == {"code": "ventas_head = ventas.head(n=2)"}
    deadline = time.monotonic() + 2
    while ("node.state", "ready") not in events and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ("node.upserted", "pending") in events and ("node.state", "ready") in events


@pytest.mark.parametrize(
    ("method", "params", "code"),
    [
        (
            "node.apply",
            {"op": {"schema_v": 1, "kind": "call", "target": "n1", "name": "_mgr"}},
            "invalid_op",
        ),
        ("node.apply", {"op": op_to_json(call("n9", "head"))}, "unknown_node"),
        ("node.summary", {"id": "nope"}, "unknown_node"),
    ],
)
def test_errors_use_framelab_codes(d, method, params, code):
    env, _ = d.handle(req(method, params), [])
    assert env["error"]["code"] == code
    assert env["error"]["i18n_key"] == f"errors.{code}"


def test_failed_node_reports_node_error(d):
    res, _ = result(d, "node.apply", {"op": op_to_json(call("n1", "astype", dtype={"b": "int64"}))})
    env, _ = d.handle(req("node.summary", {"id": res["node"]["id"]}), [])
    assert env["error"]["code"] == "node_error"


@pytest.mark.parametrize(
    "params",
    [{"id": "n1", "offset": "abc"}, {"id": "n1", "limit": -5}, {"id": "n1", "col_stop": "x"}, {}],
)
def test_bad_window_params_are_bad_requests(d, params):
    env, _ = d.handle(req("node.window", params), [])
    assert env["error"]["code"] in ("bad_request", "unknown_node")
    assert env["error"]["code"] != "internal"
