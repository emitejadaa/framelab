import threading

import numpy as np
import pandas as pd
import pytest

import framelab.session.core as core
from framelab.naming import RootSpec
from framelab.ops.build import call, getitem
from framelab.session import NodeError, NodeState, Session

VENTAS = pd.DataFrame({"pais": ["AR", "UY", "AR"], "monto": [10.0, np.nan, 30.0]})


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS.copy())])
    yield session
    session.close()


def block_lane(session):
    gate = threading.Event()
    session._lane.submit(gate.wait, 10)
    return gate


def test_cancel_a_queued_node_blocks_its_children(s):
    gate = block_lane(s)
    a = s.apply(call("n1", "head", n=2))
    b = s.apply(call(a.id, "tail", n=1))
    assert s.cancel(a.id)
    assert s.node(a.id).state is NodeState.CANCELLED
    gate.set()
    with pytest.raises(NodeError):
        s.wait(b.id, timeout=5)
    assert s.node(b.id).state is NodeState.BLOCKED


def test_cancel_a_running_node_discards_its_result(s, monkeypatch):
    started, release = threading.Event(), threading.Event()
    real = core.run_statement

    def slow(code, result, env):
        started.set()
        release.wait(5)
        return real(code, result, env)

    monkeypatch.setattr(core, "run_statement", slow)
    a = s.apply(call("n1", "head", n=2))
    assert started.wait(5)
    assert s.cancel(a.id)
    assert s.node(a.id).info()["cancelling"] is True
    release.set()
    with pytest.raises(NodeError, match="cancelled"):
        s.wait(a.id, timeout=5)
    assert s.node(a.id).state is NodeState.CANCELLED


def test_waiters_of_a_cancelled_node_get_node_error(s):
    """Review focus 4: waiters see NodeError, children block, retry heals the branch."""
    gate = block_lane(s)
    a = s.apply(call("n1", "head", n=2))
    b = s.apply(call(a.id, "tail", n=1))
    errors: list[str] = []

    def waiter():
        try:
            s.wait(a.id, timeout=5)
        except Exception as exc:  # noqa: BLE001 - recording what the waiter sees
            errors.append(type(exc).__name__)

    thread = threading.Thread(target=waiter)
    thread.start()
    s.cancel(a.id)
    gate.set()
    thread.join(5)
    assert errors == ["NodeError"]
    with pytest.raises(NodeError):
        s.wait(b.id, timeout=5)
    assert s.retry(a.id) == [a.id, b.id]
    pd.testing.assert_frame_equal(s.wait(b.id, timeout=5), VENTAS.head(2).tail(1))


def test_ready_nodes_cannot_be_cancelled(s):
    a = s.apply(call("n1", "head", n=1))
    s.wait(a.id)
    assert not s.cancel(a.id)
    assert s.retry(a.id) == []


def test_clear_failed_removes_errors_and_blocked_children(s):
    bad = s.apply(getitem("n1", "no_existe"))
    child = s.apply(call(bad.id, "head", n=1))
    ok = s.apply(call("n1", "head", n=1))
    with pytest.raises(NodeError):
        s.wait(child.id, timeout=5)
    s.wait(ok.id)
    out = s.clear_failed()
    assert out["ids"] == [bad.id, child.id]
    assert ok.id in s and bad.id not in s
    assert s.undo() and bad.id in s and child.id in s
