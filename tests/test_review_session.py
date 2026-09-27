"""Session regressions found by the multi-agent review."""

import contextlib
import threading
import time

import numpy as np
import pandas as pd
import pytest

import framelab.session.core as core
from framelab.engine.guards import GuardError
from framelab.naming import RootSpec
from framelab.ops import Op
from framelab.ops.build import call, col, mul, setcol
from framelab.ops.values import Lit, NodeRef
from framelab.session import NodeState, Session

FRAME = pd.DataFrame({"a": np.arange(1000.0)})


def wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def tiny():
    s = Session([RootSpec("v", FRAME.copy())], cache_bytes=1)
    yield s
    s.close()


def freed(s):
    node = s.apply(setcol("n1", "b", mul(col("a"), 2)))
    assert wait_for(lambda: s.node(node.id).state is NodeState.FREED)
    return node


def test_a_parent_recomputed_for_a_child_can_be_waited_for(tiny):
    s = tiny
    a = freed(s)
    s.set_pins([a.id])
    b = s.apply(call(a.id, "sum", numeric_only=True))
    s.wait(b.id, 5)
    assert s.node(a.id).state is NodeState.READY
    assert list(s.wait(a.id, 5).columns) == ["a", "b"]


def test_sorting_a_table_keeps_no_sorted_copies():
    frame = pd.DataFrame(np.random.default_rng(0).random((1000, 4)), columns=list("abcd"))
    s = Session([RootSpec("v", frame)])
    try:
        for column in range(4):
            for ascending in (True, False):
                s.window("n1", 0, 10, sort=(column, ascending))
        sorted_encoders = [k for k in s._encoders if k.startswith("n1|")]
        assert len(sorted_encoders) == 1
        data, meta = s.window("n1", 0, 3, sort=(1, False))
        assert meta["nrows_total"] == 1000
        assert all(e.frame is s.wait("n1") for e in s._encoders.values())
    finally:
        s.close()


def test_renaming_a_node_while_it_computes(monkeypatch):
    s = Session([RootSpec("v", FRAME.copy())])
    started, release = threading.Event(), threading.Event()
    check = core.guards.check

    def slow_check(*args, **kwargs):
        if threading.current_thread() is not threading.main_thread():  # the compute lane
            started.set()
            release.wait(5)
        return check(*args, **kwargs)

    monkeypatch.setattr(core.guards, "check", slow_check)
    try:
        node = s.apply(call("n1", "head", n=5), force=False)
        assert started.wait(5)
        s.rename(node.id, "top5")
        release.set()
        assert len(s.wait(node.id, 5)) == 5
        assert s.node(node.id).name == "top5"
    finally:
        release.set()
        s.close()


def test_snapshots_and_figure_edits_from_two_threads_do_not_deadlock():
    s = Session([RootSpec("v", FRAME.copy())])
    fig = s.plots.create("n1")
    node = s.apply(call("n1", "head", n=2))
    stop = time.monotonic() + 0.5

    def snapshots():
        i = 0
        while time.monotonic() < stop:
            s.snapshot()
            s.rename(node.id, f"top_{i % 2}")
            i += 1

    def edits():
        i = 0
        while time.monotonic() < stop:
            spec = s.plots.get(fig["id"])["spec"]
            spec["width"] = 5 + i % 7
            s.plots.update(fig["id"], spec)
            i += 1

    threads = [threading.Thread(target=snapshots), threading.Thread(target=edits)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    try:
        assert not any(t.is_alive() for t in threads)
    finally:
        s.close()


@pytest.fixture
def duplicated():
    left = pd.DataFrame({"x": 1.0}, index=np.zeros(2000, int))
    right = pd.DataFrame({"y": 2.0}, index=np.zeros(2000, int))
    s = Session([RootSpec("left", left), RootSpec("right", right)], guard_bytes=1_000_000)
    yield s
    s.close()


def test_join_is_guarded(duplicated):
    join = Op("call", "n1", "join", args=(NodeRef("n2"),))
    with pytest.raises(GuardError):
        duplicated.preview(join)
    node = duplicated.apply(join, force=True)  # "run it anyway" still works
    assert node.id


def test_index_merges_are_guarded(duplicated):
    both = (("left_index", Lit(True)), ("right_index", Lit(True)))
    with pytest.raises(GuardError):
        duplicated.preview(Op("call", "n1", "merge", args=(NodeRef("n2"),), kwargs=both))


def test_index_merge_estimates_are_exact():
    from framelab.engine.guards import estimate

    left = pd.DataFrame({"k": [1, 1, 2], "x": [0.0, 1.0, 2.0]})
    right = pd.DataFrame({"y": [5.0, 6.0]}, index=[1, 3])
    values = {"n1": left, "n2": right}
    op = Op(
        "call",
        "n1",
        "merge",
        args=(NodeRef("n2"),),
        kwargs=(("left_on", Lit("k")), ("right_index", Lit(True)), ("how", Lit("outer"))),
    )
    rows = len(left.merge(right, left_on="k", right_index=True, how="outer"))
    assert estimate(op, values).rows == rows
    other = pd.DataFrame({"z": [7.0, 8.0, 9.0]}, index=[1, 1, 2])
    join = Op("call", "n1", "join", args=(NodeRef("n2"),), kwargs=(("on", Lit("k")),))
    assert estimate(join, {"n1": left, "n2": other}).rows == len(left.join(other, on="k"))
    plain = Op("call", "n2", "join", args=(NodeRef("n1"),), kwargs=(("how", Lit("inner")),))
    assert estimate(plain, {"n1": other, "n2": right}).rows == len(right.join(other, how="inner"))


def test_undo_then_redo_of_a_create_keeps_its_figure_layers():
    s = Session([RootSpec("v", FRAME.copy())])
    try:
        node = s.apply(setcol("n1", "b", mul(col("a"), 2)))
        s.wait(node.id, 5)
        fig = s.plots.create(node.id)
        spec = fig["spec"]
        spec["axes"][0]["layers"] = [{"kind": "line", "source": node.id, "y": [{"col": "b"}]}]
        s.plots.update(fig["id"], spec)
        assert s.undo() and s.redo()
        state = s.plots.get(fig["id"])
        assert [ly["source"] for ly in state["spec"]["axes"][0]["layers"]] == [node.id]
        assert state["can_undo"]
    finally:
        s.close()


def test_a_node_deleted_while_it_is_recomputed_leaves_nothing_behind(tiny, monkeypatch):
    s = tiny
    a = freed(s)
    started, release = threading.Event(), threading.Event()
    run = core.run_statement

    def slow(*args, **kwargs):
        started.set()
        release.wait(5)
        return run(*args, **kwargs)

    monkeypatch.setattr(core, "run_statement", slow)

    def wait():
        with contextlib.suppress(Exception):
            s.wait(a.id, 5)

    waiter = threading.Thread(target=wait)
    waiter.start()
    assert started.wait(5)
    s.delete(a.id)
    release.set()
    waiter.join(5)
    assert a.id not in s._results
    assert a.id not in s._cache._sizes


def test_a_failed_recompute_can_be_tried_again(tiny, monkeypatch):
    s = tiny
    a = freed(s)
    run = core.run_statement
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise MemoryError("no room")
        return run(*args, **kwargs)

    monkeypatch.setattr(core, "run_statement", flaky)
    with pytest.raises(MemoryError):
        s.wait(a.id, 5)
    assert s.node(a.id).state is NodeState.FREED
    assert list(s.wait(a.id, 5).columns) == ["a", "b"]
