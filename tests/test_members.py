"""What each node offers from the pandas catalog."""

import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call, getitem, ref_col
from framelab.session import NodeKind, Session
from framelab.transport.dispatcher import Dispatcher

FRAME = pd.DataFrame(
    {
        "fecha": pd.date_range("2024-01-01", periods=6, freq="D"),
        "pais": pd.array(["AR", "UY", "AR", None, "BR", "AR"], dtype="str"),
        "monto": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "cat": pd.Categorical(list("ababab")),
    }
)


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", FRAME)])
    yield session
    session.close()


def owners(members):
    return {(m["accessor"][0] if m["accessor"] else m["owner"], m["name"]) for m in members}


def test_dataframe_members(s):
    names = {m["name"] for m in s.members("n1")}
    assert {"sort_values", "head", "T", "nlargest", "describe"} <= names
    assert not names & {"to_csv", "insert", "pop", "update", "eval", "query", "plot", "to_pickle"}


def test_series_accessors_follow_the_dtype(s):
    text = owners(s.members(s.apply(getitem("n1", "pais")).id))
    assert ("str", "upper") in text and ("Series", "value_counts") in text
    assert not any(owner in ("dt", "cat") for owner, _ in text)
    dates = owners(s.members(s.apply(getitem("n1", "fecha")).id))
    assert ("dt", "year") in dates and not any(owner == "str" for owner, _ in dates)
    cats = owners(s.members(s.apply(getitem("n1", "cat")).id))
    assert ("cat", "codes") in cats
    numbers = owners(s.members(s.apply(getitem("n1", "monto")).id))
    assert not any(owner in ("str", "dt", "cat") for owner, _ in numbers)


def test_groupby_members(s):
    grouped = s.apply(call("n1", "groupby", by=ref_col("pais")))
    names = {m["name"] for m in s.members(grouped.id)}
    assert {"sum", "mean", "agg", "size"} <= names
    assert all(m["owner"] == "DataFrameGroupBy" for m in s.members(grouped.id))


def test_windows_are_nodes_with_members(s):
    monto = s.apply(getitem("n1", "monto"))
    rolling = s.apply(call(monto.id, "rolling", 2))
    s.wait(rolling.id)
    assert s.node(rolling.id).kind is NodeKind.WINDOW
    assert "mean" in {m["name"] for m in s.members(rolling.id)}
    assert s.summary(rolling.id)["kind"] == "Window"
    mean = s.apply(call(rolling.id, "mean"))
    pd.testing.assert_series_equal(s.wait(mean.id), FRAME["monto"].rolling(2).mean())
    resampled = s.apply(
        call(s.apply(call("n1", "set_index", ref_col("fecha"))).id, "resample", "2D")
    )
    s.wait(resampled.id)
    assert s.node(resampled.id).kind is NodeKind.WINDOW
    assert "sum" in {m["name"] for m in s.members(resampled.id)}


def test_node_members_method(s):
    env, _ = Dispatcher(s).handle(
        {"v": 1, "id": "1", "type": "req", "method": "node.members", "params": {"id": "n1"}}, []
    )
    head = next(m for m in env["result"]["members"] if m["name"] == "head")
    assert head["params"][0]["name"] == "n" and head["accessor"] == []
