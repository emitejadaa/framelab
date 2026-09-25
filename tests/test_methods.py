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


def test_op_preview_renders_without_creating_a_node(d):
    op = op_to_json(call("n1", "head", n=5))
    res, _ = result(d, "op.preview", {"op": op})
    assert res == {
        "name": "ventas_head",
        "code": "ventas_head = ventas.head(n=5)",
        "label": "head(n=5)",
    }
    assert [n.name for n in d.session.nodes()] == ["ventas"]


def test_op_preview_reports_invalid_ops(d):
    env, _ = d.handle(
        req(
            "op.preview",
            {"op": {"schema_v": 1, "kind": "call", "target": "n1", "name": "to_pickle"}},
        ),
        [],
    )
    assert env["error"]["code"] == "invalid_op"


def test_summary_columns_carry_encoded_labels(d):
    res, _ = result(d, "node.summary", {"id": "n1"})
    assert [c["label"] for c in res["columns"]] == ["a", "b"]


def test_plotter_methods(d):
    catalog, _ = result(d, "plot.catalog", {})
    assert "line" in [k["key"] for k in catalog["kinds"]]
    fields, _ = result(d, "plot.fields", {"id": "ventas"})
    assert [f["text"] for f in fields["fields"]] == ["a", "b"] and fields["index"]["kind"] == "num"
    fig, _ = result(d, "figure.create", {"source": "n1"})
    assert fig["id"] == "f1" and fig["spec"]["name"] == "fig_ventas"
    spec = fig["spec"]
    spec["axes"][0]["layers"] = [
        {"kind": "bar", "source": "n1", "x": {"col": "b"}, "y": [{"col": "a"}]}
    ]
    state, _ = result(d, "figure.update", {"id": "f1", "spec": spec})
    assert state["version"] == 2 and state["can_undo"]
    meta, bufs = result(
        d, "figure.render", {"id": "f1", "width_px": 300, "height_px": 200, "dpr": 2}
    )
    assert bufs[0].startswith(b"\x89PNG") and meta["errors"] == [] and meta["width"] <= 600
    code, _ = result(d, "figure.code", {"id": "f1", "mode": "figure"})
    assert 'ax_ventas.bar(ventas["b"], ventas["a"])' in code["code"]
    meta, bufs = result(d, "figure.export", {"id": "f1", "format": "svg", "download": True})
    assert meta["path"] is None and b"<svg" in bufs[0][:500]
    assert result(d, "session.snapshot", {})[0]["figures"][0]["name"] == "fig_ventas"
    env, _ = d.handle(req("figure.update", {"id": "f1", "spec": {"name": "x", "axes": "no"}}), [])
    assert env["error"]["code"] == "invalid_figure"
    env, _ = d.handle(req("figure.get", {"id": "f9"}), [])
    assert env["error"]["code"] == "unknown_figure"
    result(d, "figure.delete", {"id": "f1"})
    assert result(d, "session.snapshot", {})[0]["figures"] == []


def test_formula_and_delete_methods(d):
    ok, _ = result(d, "formula.parse", {"id": "n1", "text": "(a + 1) * 2"})
    assert ok["ok"] and ok["expr"]["t"] == "arith"
    bad, _ = result(d, "formula.parse", {"id": "n1", "text": "a * nope"})
    assert not bad["ok"] and "nope" in bad["message"] and bad["offset"] == 4
    op = {"schema_v": 1, "kind": "setitem", "target": "n1", "name": "", "accessor": [], "args": [],
          "kwargs": [], "key": "c", "expr": ok["expr"]}  # fmt: skip
    node, _ = result(d, "node.apply", {"op": op})
    child, _ = result(d, "node.apply", {"op": op_to_json(call(node["node"]["id"], "head", n=1))})
    preview, _ = result(d, "node.delete_preview", {"id": node["node"]["id"]})
    assert preview["ids"] == [node["node"]["id"], child["node"]["id"]]
    out, _ = result(d, "node.delete", {"id": node["node"]["id"]})
    assert out["ids"] == preview["ids"]
    env, _ = d.handle(req("node.delete", {"id": "n1"}), [])
    assert env["error"]["code"] == "cannot_delete"
