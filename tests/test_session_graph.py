import time

import numpy as np
import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call, col, getitem, gt, method, ref_col, setcol, where
from framelab.session import NodeError, NodeKind, NodeState, Session, UnknownNode


@pytest.fixture
def ventas():
    return pd.DataFrame(
        {
            "pais": ["AR", "UY", "AR", "BR"],
            "monto": [10.0, np.nan, 30.0, 5.0],
            "cantidad": [1, 2, 3, 4],
        }
    )


@pytest.fixture
def session(ventas):
    s = Session([RootSpec("ventas", ventas)])
    yield s
    s.close()


def test_roots_are_ready_nodes(session, ventas):
    root = session.node("ventas")
    assert root.id == "n1" and root.state is NodeState.READY and root.kind is NodeKind.DATAFRAME
    assert root.shape == (4, 3) and root.is_root
    pd.testing.assert_frame_equal(session["ventas"], ventas)


def test_apply_creates_an_immutable_child(session, ventas):
    node = session.apply(call("n1", "head", n=2))
    assert node.id == "n2" and node.name == "ventas_head" and node.parents == ("n1",)
    assert node.label == "head(n=2)"
    pd.testing.assert_frame_equal(session.wait("ventas_head"), ventas.head(2))
    assert session.node("n2").state is NodeState.READY and session.node("n2").shape == (2, 3)


def test_kinds(session):
    s = session.apply(getitem("n1", "monto"))
    g = session.apply(call("n1", "groupby", by=ref_col("pais")))
    v = session.apply(call(s.id, "sum"))
    i = session.apply(call("n1", "keys"))
    for n in (s, g, v, i):
        session.wait(n.id)
    assert session.node(s.id).kind is NodeKind.SERIES
    assert session.node(g.id).kind is NodeKind.GROUPBY
    assert session.node(v.id).kind is NodeKind.VALUE
    assert session.node(i.id).kind is NodeKind.INDEX


def test_errors_become_error_nodes_and_children_are_blocked(session):
    bad = session.apply(call("n1", "astype", dtype={"monto": "int64"}))
    with pytest.raises(NodeError, match=bad.name):
        session.wait(bad.id)
    node = session.node(bad.id)
    assert node.state is NodeState.ERROR and node.error.type in {"IntCastingNaNError", "ValueError"}
    child = session.apply(call(bad.id, "head", n=1))
    with pytest.raises(NodeError):
        session.wait(child.id)
    assert session.node(child.id).state is NodeState.BLOCKED
    ok = session.apply(call("n1", "tail", n=1))
    assert len(session.wait(ok.id)) == 1


def test_user_mutating_their_frame_changes_nothing(session, ventas):
    head = session.apply(call("n1", "head", n=2))
    head_before = session.wait(head.id).copy()
    root_before = session["ventas"].copy()
    ventas.loc[0, "monto"] = -999.0
    ventas["nuevo"] = 1
    pd.testing.assert_frame_equal(session.wait(head.id), head_before)
    pd.testing.assert_frame_equal(session["ventas"], root_before)
    later = session.apply(call("n1", "head", n=1))
    assert session.wait(later.id).loc[0, "monto"] == 10.0


def test_parents_are_never_mutated(session, ventas):
    snapshot = ventas.copy()
    n = session.apply(setcol("n1", "pais", method(col("pais"), "lower", accessor=("str",))))
    session.wait(n.id)
    pd.testing.assert_frame_equal(session["ventas"], snapshot)


def test_unknown_parent_and_duplicate_names(session):
    with pytest.raises(UnknownNode):
        session.apply(call("n99", "head"))
    session.apply(call("n1", "head", n=1), name="primero")
    with pytest.raises(ValueError):
        session.apply(call("n1", "head", n=2), name="primero")


def test_events_are_emitted(session):
    events = []
    off = session.subscribe(lambda method, params: events.append((method, params["state"])))
    n = session.apply(call("n1", "head", n=1))
    session.wait(n.id)
    deadline = time.monotonic() + 2
    while ("node.state", "ready") not in events and time.monotonic() < deadline:
        time.sleep(0.01)
    off()
    assert events[0] == ("node.upserted", "pending")
    assert ("node.state", "computing") in events and ("node.state", "ready") in events


def test_lineage_and_code(session):
    f = session.apply(where("n1", gt(col("monto"), 7)))
    s = session.apply(call(f.id, "sort_values", by=ref_col("monto")))
    assert session.lineage(s.id) == ["n1", f.id, s.id]
    assert (
        session.code(s.id, mode="step")
        == 'ventas_filt_sorted = ventas_filt.sort_values(by="monto")'
    )
    script = session.code(s.id)
    assert script.splitlines()[0] == "import pandas as pd" or script.startswith("# ventas")
    assert 'ventas_filt = ventas[ventas["monto"] > 7]' in script
    assert script.rstrip().endswith('ventas_filt_sorted = ventas_filt.sort_values(by="monto")')


def test_root_with_source_expr_appears_in_script(ventas):
    s = Session([RootSpec("dfs_0", ventas, "dfs[0]")])
    n = s.apply(call("n1", "head", n=1))
    assert "dfs_0 = dfs[0]" in s.code(n.id)
    s.close()


def test_snapshot_lists_nodes(session):
    session.apply(call("n1", "head", n=1))
    snap = session.snapshot()
    assert [n["name"] for n in snap["nodes"]] == ["ventas", "ventas_head"]
    assert snap["nodes"][0] == {
        "id": "n1",
        "name": "ventas",
        "kind": "DataFrame",
        "state": "ready",
        "parents": [],
        "label": "",
        "name_auto": False,
        "shape": [4, 3],
    }


def test_a_failing_listener_does_not_break_computation(session):
    def boom(method, params):
        raise RuntimeError("listener bug")

    session.subscribe(boom)
    node = session.apply(call("n1", "head", n=1))
    assert len(session.wait(node.id, timeout=5)) == 1
    assert session.node(node.id).state is NodeState.READY
