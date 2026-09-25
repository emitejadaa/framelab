import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops import op_to_json, remap_op
from framelab.ops.build import call, col, gt, node, where
from framelab.session import Session
from framelab.session.core import CannotEdit

VENTAS = pd.DataFrame({"pais": ["AR", "UY", "AR", "BR"], "monto": [120.0, 50.0, 300.0, 45.0]})


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS.copy()), RootSpec("otros", VENTAS.head(1))])
    yield session
    session.close()


def test_remap_op_replaces_targets_and_references():
    op = call("n1", "merge", node("n2"), on="pais")
    data = op_to_json(remap_op(op, {"n1": "n5", "n2": "n6"}))
    assert data["target"] == "n5" and data["args"] == [{"t": "node", "id": "n6"}]


def test_edit_as_new_replays_the_branch(s):
    filt = s.apply(where("n1", gt(col("monto"), 100)))
    top = s.apply(call(filt.id, "head", n=2), name="top")
    total = s.apply(call(top.id, "sum", numeric_only=True))
    mapping = s.edit_as_new(filt.id, where("n1", gt(col("monto"), 48)))
    assert set(mapping) == {filt.id, top.id, total.id}
    new_top = s.node(mapping[top.id])
    assert new_top.name == "top_2" and not new_top.name_auto
    assert s.node(mapping[total.id]).parents == (new_top.id,)
    pd.testing.assert_frame_equal(s.wait(new_top.id), VENTAS[VENTAS["monto"] > 48].head(2))
    pd.testing.assert_frame_equal(s.wait(top.id), VENTAS[VENTAS["monto"] > 100].head(2))


def test_edit_without_replay_makes_only_the_sibling(s):
    filt = s.apply(where("n1", gt(col("monto"), 100)))
    s.apply(call(filt.id, "head", n=2))
    mapping = s.edit_as_new(filt.id, where("n1", gt(col("monto"), 10)), replay=False)
    assert list(mapping) == [filt.id]
    assert len(s) == 5


def test_one_undo_removes_the_whole_new_branch(s):
    filt = s.apply(where("n1", gt(col("monto"), 100)))
    s.apply(call(filt.id, "head", n=2))
    before = [n.id for n in s.nodes()]
    mapping = s.edit_as_new(filt.id, where("n1", gt(col("monto"), 10)))
    assert s.undo()
    assert [n.id for n in s.nodes()] == before
    assert s.redo() and all(new in s for new in mapping.values())


def test_roots_cannot_be_edited(s):
    with pytest.raises(CannotEdit):
        s.edit_as_new("n1", call("n2", "head", n=1))
