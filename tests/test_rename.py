import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call, node, ref_col
from framelab.session import Session
from framelab.session.core import CannotRename, NameTaken


@pytest.fixture
def s():
    ventas = pd.DataFrame({"pais": ["AR", "UY"], "monto": [1.0, 2.0]})
    clientes = pd.DataFrame({"pais": ["AR"], "nombre": ["Ana"]})
    session = Session([RootSpec("ventas", ventas), RootSpec("clientes", clientes)])
    yield session
    session.close()


def test_auto_named_children_follow_a_rename(s):
    head = s.apply(call("n1", "head", n=1))
    sorted_ = s.apply(call(head.id, "sort_values", by=ref_col("monto")))
    kept = s.apply(call(head.id, "tail", n=1), name="mi_tabla")
    assert s.rename(head.id, "top") == [head.id, sorted_.id]
    assert s.node(sorted_.id).name == "top_sorted"
    assert s.node(kept.id).name == "mi_tabla"  # edited names never follow
    assert "top_sorted = top.sort_values(" in s.code(sorted_.id)
    assert not s.node(head.id).name_auto


def test_labels_that_mention_a_renamed_node_update(s):
    merged = s.apply(call("n1", "merge", node("n2"), on="pais"))
    head = s.apply(call("n2", "head", n=1))
    merged2 = s.apply(call("n1", "merge", node(head.id), on="pais"))
    s.rename(head.id, "primeros")
    assert s.node(merged2.id).label == 'merge(primeros, on="pais")'
    assert s.node(merged2.id).name == "ventas_primeros"
    assert s.node(merged.id).name == "ventas_clientes"


def test_rename_rules(s):
    head = s.apply(call("n1", "head", n=1))
    with pytest.raises(CannotRename):
        s.rename("n1", "otra")
    with pytest.raises(NameTaken):
        s.rename(head.id, "clientes")
    assert s.rename(head.id, "1 raro!") == [head.id]
    assert s.node(head.id).name == "df_1_raro"
