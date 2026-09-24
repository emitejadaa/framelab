import ast

import pytest

from framelab.codegen.render import op_label, render_op
from framelab.ops.build import (
    and_,
    attr,
    call,
    col,
    eq,
    fn,
    func,
    getitem,
    gt,
    method,
    mul,
    node,
    not_,
    or_,
    ref_col,
    setcol,
    where,
)

NAMES = {"n1": "ventas", "n2": "clientes", "n3": "ventas_head", "n4": "ventas_tail"}


def show(op, result="out"):
    r = render_op(op, result, NAMES)
    ast.parse(r.display)
    ast.parse(r.executed)
    return r


@pytest.mark.parametrize(
    ("op", "code"),
    [
        (call("n1", "head", n=5), "out = ventas.head(n=5)"),
        (
            call("n1", "sort_values", by=ref_col("monto"), ascending=False),
            'out = ventas.sort_values(by="monto", ascending=False)',
        ),
        (
            call("n1", "sort_values", by=[ref_col("pais"), ref_col("monto")]),
            'out = ventas.sort_values(by=["pais", "monto"])',
        ),
        (
            call("n1", "rename", columns={"monto": "importe"}),
            'out = ventas.rename(columns={"monto": "importe"})',
        ),
        (call("n1", "fillna", value={"monto": 0.0}), 'out = ventas.fillna(value={"monto": 0.0})'),
        (getitem("n1", "precio unitario"), 'out = ventas["precio unitario"]'),
        (getitem("n1", ["pais", "monto"]), 'out = ventas[["pais", "monto"]]'),
        (getitem("n1", 2024), "out = ventas[2024]"),
        (getitem("n1", ("a", 1)), 'out = ventas[("a", 1)]'),
        (where("n1", gt(col("monto"), 100)), 'out = ventas[ventas["monto"] > 100]'),
        (
            where("n1", and_(eq(col("pais"), "AR"), gt(col("monto"), 100))),
            'out = ventas[(ventas["pais"] == "AR") & (ventas["monto"] > 100)]',
        ),
        (
            where(
                "n1",
                or_(method(col("pais"), "isin", ["AR", "UY"]), not_(method(col("monto"), "isna"))),
            ),
            'out = ventas[ventas["pais"].isin(["AR", "UY"]) | ~ventas["monto"].isna()]',
        ),
        (
            where("n1", not_(and_(gt(col("a"), 1), gt(col("b"), 2)))),
            'out = ventas[~((ventas["a"] > 1) & (ventas["b"] > 2))]',
        ),
        (
            call("n1", "merge", node("n2"), on="id", how="left"),
            'out = ventas.merge(clientes, on="id", how="left")',
        ),
        (
            func("concat", objs=[node("n3"), node("n4")]),
            "out = pd.concat(objs=[ventas_head, ventas_tail])",
        ),
        (attr("n1", "T"), "out = ventas.T"),
        (attr("n1", "year", accessor=("dt",)), "out = ventas.dt.year"),
        (call("n1", "upper", accessor=("str",)), "out = ventas.str.upper()"),
        (call("n1", "agg", func=fn("mean")), 'out = ventas.agg(func="mean")'),
        (call("n1", "transform", func=fn("log", "np")), "out = ventas.transform(func=np.log)"),
        (call("n1", "fillna", value=float("nan")), "out = ventas.fillna(value=np.nan)"),
    ],
)
def test_display_equals_executed_for_plain_ops(op, code):
    r = show(op)
    assert r.display == code
    assert r.executed == code


def test_setitem_shows_copy_but_runs_shallow_copy():
    r = show(setcol("n1", "total", mul(col("monto"), col("cantidad"))), result="ventas_2")
    assert r.display == (
        'ventas_2 = ventas.copy()\nventas_2["total"] = ventas_2["monto"] * ventas_2["cantidad"]'
    )
    assert r.executed == (
        "ventas_2 = ventas.copy(deep=False)\n"
        'ventas_2["total"] = ventas_2["monto"] * ventas_2["cantidad"]'
    )


def test_setitem_with_accessor_method():
    r = show(setcol("n1", "pais", method(col("pais"), "upper", accessor=("str",))), result="v2")
    assert r.display.splitlines()[1] == 'v2["pais"] = v2["pais"].str.upper()'


def test_arith_parenthesises_nested_operands():
    r = show(setcol("n1", "x", mul(col("a"), method(col("b"), "fillna", value=0))), result="v")
    assert r.display.endswith('v["x"] = v["a"] * v["b"].fillna(value=0)')


@pytest.mark.parametrize(
    ("op", "label"),
    [
        (call("n1", "head", n=5), "head(n=5)"),
        (getitem("n1", "monto"), '["monto"]'),
        (where("n1", gt(col("monto"), 100)), 'ventas["monto"] > 100'),
        (setcol("n1", "pais", method(col("pais"), "upper", accessor=("str",))), '["pais"] = …'),
        (func("concat", objs=[node("n3"), node("n4")]), "pd.concat(…)"),
        (attr("n1", "year", accessor=("dt",)), "dt.year"),
    ],
)
def test_op_label(op, label):
    assert op_label(op, NAMES) == label


def test_op_label_is_truncated():
    long = where("n1", and_(*[gt(col(f"columna_{i}"), i) for i in range(6)]))
    label = op_label(long, NAMES)
    assert len(label) <= 48 and label.endswith("…")
