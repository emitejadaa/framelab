import numpy as np
import pandas as pd
import pytest

from framelab.ops import (
    SCHEMA_VERSION,
    Col,
    GetCol,
    Lit,
    NodeRef,
    Op,
    OpError,
    This,
    op_from_json,
    op_to_json,
)
from framelab.ops.build import (
    and_,
    call,
    col,
    eq,
    func,
    getitem,
    gt,
    method,
    mul,
    node,
    not_,
    ref_col,
    setcol,
    where,
)


def roundtrip(op):
    data = op_to_json(op)
    assert data["schema_v"] == SCHEMA_VERSION
    back = op_from_json(data)
    assert back == op
    return data


def test_call_with_kwargs_roundtrip():
    op = call("n1", "sort_values", by=ref_col("monto"), ascending=False)
    assert op.kwargs == (("by", Col("monto")), ("ascending", Lit(False)))
    roundtrip(op)


def test_special_literals_roundtrip():
    op = call("n1", "fillna", value={"monto": np.nan, ("a", 1): pd.Timestamp("2024-01-01")})
    roundtrip(op)


def test_getitem_label_and_list():
    roundtrip(getitem("n1", "monto"))
    roundtrip(getitem("n1", ["a", "b"]))
    roundtrip(getitem("n1", ("x", 2024)))


def test_filter_and_setitem_roundtrip():
    cond = and_(eq(col("pais"), "AR"), gt(col("monto"), 100))
    roundtrip(where("n1", cond))
    roundtrip(setcol("n1", "total", mul(col("monto"), col("cantidad"))))
    roundtrip(setcol("n1", "pais", method(col("pais"), "upper", accessor=("str",))))
    roundtrip(where("n1", not_(method(col("pais"), "isna"))))


def test_func_with_node_list():
    op = func("concat", objs=[node("n2"), node("n3")])
    data = roundtrip(op)
    assert op.parents() == ("n2", "n3")
    assert data["target"] is None


def test_parents_include_target_and_refs():
    op = call("n1", "merge", node("n4"), on="id")
    assert op.parents() == ("n1", "n4")


@pytest.mark.parametrize(
    "bad",
    [
        Op("call", target="n1", name="_private"),
        Op("call", target="n1", name="__class__"),
        Op("call", target=None, name="head"),
        Op("call", target="n1", name="upper", accessor=("evil",)),
        Op("attr", target="n1", name="not an identifier"),
        Op("getitem", target="n1"),
        Op("filter", target="n1"),
        Op("setitem", target="n1", key="c"),
        Op("func", target="n1", name="concat"),
        Op("func", name="read_csv"),
        Op("nope", target="n1"),  # type: ignore[arg-type]
    ],
)
def test_validation_rejects(bad):
    with pytest.raises(OpError):
        bad.validate()


def test_from_json_rejects_unknown_tags_and_versions():
    data = op_to_json(getitem("n1", "a"))
    with pytest.raises(OpError):
        op_from_json({**data, "schema_v": 99})
    with pytest.raises(OpError):
        op_from_json({**data, "key": {"$": "pickle", "v": "..."}})
    bad_expr = op_to_json(where("n1", eq(col("a"), 1)))
    bad_expr["expr"]["t"] = "lambda"
    with pytest.raises(OpError):
        op_from_json(bad_expr)


def test_comparison_operator_is_validated():
    op = where("n1", eq(col("a"), 1))
    data = op_to_json(op)
    data["expr"]["op"] = "is"
    with pytest.raises(OpError):
        op_from_json(data)


def test_values_are_hashable_and_frozen():
    v = GetCol(This(), "a")
    assert hash(v) == hash(GetCol(This(), "a"))
    assert NodeRef("n1") == NodeRef("n1")
