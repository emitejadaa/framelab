import numpy as np
import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call, ref_col
from framelab.session import Session

VENTAS = pd.DataFrame({"pais": ["AR", "UY", "AR", "BR"], "monto": [10.0, np.nan, 30.0, 5.0]})


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS.copy())])
    yield session
    session.close()


def state(session):
    return [(n.id, n.name, n.name_auto) for n in session.nodes()]


def test_undo_create_and_redo_restores_the_same_node(s):
    head = s.apply(call("n1", "head", n=2))
    s.wait(head.id)
    assert s.snapshot()["history"] == {"can_undo": True, "can_redo": False}
    assert s.undo() and head.id not in s
    assert s.snapshot()["history"] == {"can_undo": False, "can_redo": True}
    assert s.redo()
    assert s.node(head.id).name == "ventas_head" and s.node(head.id).name_auto
    pd.testing.assert_frame_equal(s.wait(head.id), VENTAS.head(2))


def test_undo_delete_restores_nodes_and_figure_layers(s):
    head = s.apply(call("n1", "head", n=3))
    last = s.apply(call(head.id, "tail", n=1), name="ultima")
    fig = s.plots.create(head.id)
    spec = fig["spec"]
    spec["axes"][0]["layers"] = [
        {"kind": "bar", "source": head.id, "x": {"col": "pais"}, "y": [{"col": "monto"}]}
    ]
    s.plots.update(fig["id"], spec)
    s.delete(head.id)
    assert s.plots.get(fig["id"])["spec"]["axes"][0]["layers"] == []
    assert s.undo()
    assert s.node(last.id).name == "ultima" and not s.node(last.id).name_auto
    assert s.plots.get(fig["id"])["spec"]["axes"][0]["layers"][0]["source"] == head.id
    pd.testing.assert_frame_equal(s.wait(last.id), VENTAS.head(3).tail(1))
    assert s.redo() and head.id not in s and last.id not in s


def test_undo_rename_restores_every_name(s):
    head = s.apply(call("n1", "head", n=1))
    srt = s.apply(call(head.id, "sort_values", by=ref_col("monto")))
    s.rename(head.id, "top")
    assert s.undo()
    assert s.node(head.id).name == "ventas_head" and s.node(head.id).name_auto
    assert s.node(srt.id).name == "ventas_head_sorted"
    assert s.redo() and s.node(srt.id).name == "top_sorted"


def test_new_changes_clear_redo(s):
    s.apply(call("n1", "head", n=1))
    s.undo()
    s.apply(call("n1", "tail", n=1))
    assert not s.redo()


def test_batches_are_one_step(s):
    with s.batch():
        a = s.apply(call("n1", "head", n=2))
        b = s.apply(call(a.id, "tail", n=1))
    assert s.undo() and a.id not in s and b.id not in s
    assert not s.undo()


def test_undo_redo_survive_mixed_changes(s):
    """Review focus 1: undo everything, redo everything, same graph and values."""
    a = s.apply(call("n1", "head", n=3))
    b = s.apply(call(a.id, "tail", n=2))
    s.rename(b.id, "cola")
    c = s.apply(call("n1", "tail", n=1))
    s.delete(a.id)
    final = state(s)
    for _ in range(4):
        assert s.undo()
    assert state(s) == [("n1", "ventas", False), (a.id, "ventas_head", True)]
    assert s.undo() and state(s) == [("n1", "ventas", False)]
    assert not s.undo()
    for _ in range(5):
        assert s.redo()
    assert state(s) == final
    pd.testing.assert_frame_equal(s.wait(c.id), VENTAS.tail(1))
