import threading

import numpy as np
import pandas as pd
import pytest

from framelab.engine.guards import GuardError, estimate
from framelab.naming import RootSpec
from framelab.ops.build import call, func, getitem, node, ref_col
from framelab.session import NodeError, Session

LEFT = pd.DataFrame({"k": [1, 1, 2, 3, np.nan], "a": range(5)})
RIGHT = pd.DataFrame({"k": [1, 1, 1, 2, 4, np.nan], "b": range(6)})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"on": "k", "how": "inner"},
        {"on": "k", "how": "left"},
        {"on": "k", "how": "right"},
        {"on": "k", "how": "outer"},
        {"how": "cross"},
        {"how": "inner"},  # default keys: the shared columns
    ],
)
def test_merge_estimates_are_exact(kwargs):
    est = estimate(call("n1", "merge", node("n2"), **kwargs), {"n1": LEFT, "n2": RIGHT})
    assert est is not None and est.rows == len(LEFT.merge(RIGHT, **kwargs))


def test_left_on_right_on_and_function_merge():
    right = RIGHT.rename(columns={"k": "kk"})
    op = call("n1", "merge", node("n2"), left_on="k", right_on="kk", how="left")
    assert estimate(op, {"n1": LEFT, "n2": right}).rows == len(
        LEFT.merge(right, left_on="k", right_on="kk", how="left")
    )
    op = func("merge", node("n1"), node("n2"), on="k")
    assert estimate(op, {"n1": LEFT, "n2": RIGHT}).rows == len(pd.merge(LEFT, RIGHT, on="k"))


def test_reshaping_estimates():
    frame = pd.DataFrame(
        {"g": ["a", "b", "a"], "h": ["x", "y", "y"], "v": [1, 2, 3], "l": [[1, 2], [], [3]]}
    )
    dummies = estimate(func("get_dummies", node("n1"), columns=["g", "h"]), {"n1": frame})
    assert (dummies.rows, dummies.columns) == pd.get_dummies(frame, columns=["g", "h"]).shape
    exploded = estimate(call("n1", "explode", "l"), {"n1": frame})
    assert exploded.rows == len(frame.explode("l"))
    pivot = estimate(
        call("n1", "pivot_table", index=ref_col("g"), columns=ref_col("h"), values=ref_col("v")),
        {"n1": frame},
    )
    assert (pivot.rows, pivot.columns) == frame.pivot_table(
        index="g", columns="h", values="v"
    ).shape


def test_big_merge_is_refused_before_creating_a_node():
    s = Session([RootSpec("left", LEFT), RootSpec("right", RIGHT)], guard_bytes=100)
    try:
        with pytest.raises(GuardError) as info:
            s.apply(call("n1", "merge", node("n2"), on="k"))
        assert info.value.code == "too_big" and info.value.rows == 8 and len(s) == 2
        with pytest.raises(GuardError):
            s.preview(call("n1", "merge", node("n2"), on="k"))
        merged = s.apply(call("n1", "merge", node("n2"), on="k"), force=True)
        assert len(s.wait(merged.id)) == 8 and s.node(merged.id).force
    finally:
        s.close()


def test_guard_runs_when_parents_were_not_ready():
    s = Session([RootSpec("left", LEFT), RootSpec("right", RIGHT)], guard_bytes=100)
    try:
        gate = threading.Event()
        s._lane.submit(gate.wait, 10)
        head = s.apply(call("n1", "head", n=5))
        merged = s.apply(call(head.id, "merge", node("n2"), on="k"))
        gate.set()
        with pytest.raises(NodeError, match="GuardError"):
            s.wait(merged.id, timeout=5)
    finally:
        s.close()


def test_string_aggregation_guard():
    frame = pd.DataFrame(
        {"pais": ["AR", "AR", "UY"], "nombre": ["a", "b", "c"], "monto": [1.0, 2.0, 3.0]}
    )
    s = Session([RootSpec("ventas", frame)])
    try:
        grouped = s.apply(call("n1", "groupby", by=ref_col("pais")))
        s.wait(grouped.id)  # guards run before creating a node once the parents are ready
        with pytest.raises(GuardError) as info:
            s.apply(call(grouped.id, "sum"))
        assert info.value.code == "string_aggregation" and "nombre" in str(info.value)
        ok = s.apply(call(grouped.id, "sum", numeric_only=True))
        assert list(s.wait(ok.id).columns) == ["monto"]
        chosen = s.apply(getitem(grouped.id, ["monto"]))
        s.wait(s.apply(call(chosen.id, "sum")).id)
        forced = s.apply(call(grouped.id, "sum"), force=True)
        assert s.wait(forced.id).loc["AR", "nombre"] == "ab"
    finally:
        s.close()
