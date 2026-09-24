import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.options import build_default_registry
from framelab.session import Session


def make(**frames):
    return Session([RootSpec(k, v, None) for k, v in frames.items()], build_default_registry())


def test_snapshot_lists_roots_with_shape():
    ventas = pd.DataFrame({"a": range(1000), "b": 0, "c": 0, "d": 0, "e": 0})
    s = make(ventas=ventas, precios=ventas["a"])
    snap = s.snapshot()
    assert snap["rev"] == 0
    assert snap["session_id"] == s.id
    assert snap["roots"] == [
        {"id": "n1", "name": "ventas", "kind": "DataFrame", "shape": [1000, 5]},
        {"id": "n2", "name": "precios", "kind": "Series", "shape": [1000]},
    ]
    assert any(o["key"] == "general.theme" for o in snap["options"])


def test_roots_are_frozen_against_later_mutation():
    ventas = pd.DataFrame({"a": [1, 2, 3]})
    s = make(ventas=ventas)
    ventas.loc[0, "a"] = 99
    assert s["ventas"].loc[0, "a"] == 1


def test_rejects_non_pandas():
    with pytest.raises(TypeError, match="DataFrame or Series"):
        make(x=[1, 2, 3])


def test_mapping_protocol_and_repr():
    s = make(ventas=pd.DataFrame({"a": [1]}))
    assert "ventas" in s and len(s) == 1 and s.names == ["ventas"] and list(s) == ["ventas"]
    assert "ventas" in repr(s)


def test_source_expr_is_kept():
    s = Session([RootSpec("dfs_0", pd.DataFrame({"a": [1]}), "dfs[0]")])
    assert s.source_expr("dfs_0") == "dfs[0]"
