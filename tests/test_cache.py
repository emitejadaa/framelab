import threading
import time

import numpy as np
import pandas as pd
import pytest

from framelab.engine.cache import ResultCache, buffers, value_bytes
from framelab.naming import RootSpec
from framelab.ops.build import call, col, mul, setcol
from framelab.session import NodeState, Session

FRAME = pd.DataFrame({"a": np.arange(1000.0), "s": [f"x{i}" for i in range(1000)]})


def wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_views_of_the_roots_cost_nothing():
    roots = {address for address, _ in buffers(FRAME)}
    assert value_bytes(FRAME["a"], roots) == 0
    assert value_bytes(FRAME.iloc[:10], roots) == 0
    assert 0 < value_bytes(FRAME.head(10), roots) <= 80  # pandas 3 head() copies numeric columns
    assert value_bytes(FRAME["a"] * 2, roots) >= 8000


def test_victims_are_least_recently_used_and_never_pinned():
    cache = ResultCache(budget=100)
    for nid in ("n2", "n3", "n4"):
        cache.add(nid, 60)
    cache.touch("n2")
    cache.pinned = {"n3"}
    assert cache.victims() == ["n4", "n2"]


@pytest.fixture
def tiny_cache():
    s = Session([RootSpec("v", FRAME.copy())], cache_bytes=1)
    yield s
    s.close()


def test_evicted_nodes_are_recomputed_when_used(tiny_cache):
    s = tiny_cache
    doubled = s.apply(setcol("n1", "b", mul(col("a"), 2)))
    expected = FRAME.assign(b=FRAME["a"] * 2)
    pd.testing.assert_frame_equal(s.wait(doubled.id), expected)
    assert wait_for(lambda: s.node(doubled.id).state is NodeState.FREED)
    pd.testing.assert_frame_equal(s.wait(doubled.id, timeout=5), expected)
    assert s.node("n1").state is NodeState.READY  # roots are never freed


def test_pinned_nodes_stay(tiny_cache):
    s = tiny_cache
    gate = threading.Event()
    s._lane.submit(gate.wait, 10)
    doubled = s.apply(setcol("n1", "b", mul(col("a"), 2)))
    s.set_pins([doubled.id])
    gate.set()
    s.wait(doubled.id, timeout=5)
    time.sleep(0.05)
    assert s.node(doubled.id).state is NodeState.READY


def test_evicted_parent_is_recomputed_for_a_queued_child(tiny_cache):
    """Review focus 2: children and table windows recompute freed parents transparently."""
    s = tiny_cache
    doubled = s.apply(setcol("n1", "b", mul(col("a"), 2)))
    s.wait(doubled.id)
    assert wait_for(lambda: s.node(doubled.id).state is NodeState.FREED)
    total = s.apply(call(doubled.id, "sum", numeric_only=True))
    assert s.wait(total.id, timeout=5)["b"] == FRAME["a"].sum() * 2
    data, meta = s.window(doubled.id, offset=0, limit=5)
    assert meta["nrows_total"] == 1000 and data


def test_figures_draw_freed_sources(tiny_cache):
    s = tiny_cache
    doubled = s.apply(setcol("n1", "b", mul(col("a"), 2)))
    s.wait(doubled.id)
    assert wait_for(lambda: s.node(doubled.id).state is NodeState.FREED)
    fig = s.plots.create(doubled.id)
    spec = fig["spec"]
    spec["axes"][0]["layers"] = [{"kind": "line", "source": doubled.id, "y": [{"col": "b"}]}]
    s.plots.update(fig["id"], spec)
    png, meta = s.plots.render(fig["id"], width_px=200, height_px=150)
    assert png.startswith(b"\x89PNG") and meta["errors"] == []
