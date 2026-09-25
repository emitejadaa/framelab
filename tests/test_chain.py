"""Chained style: single-use steps fold into one expression, and the code stays faithful."""

import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call, col, func, getitem, gt, mul, node, ref_col, setcol, where
from framelab.options import build_default_registry
from framelab.session import Session
from test_fidelity import CASES, _resolve, assert_same, make_frames


def chained_session():
    registry = build_default_registry()
    registry.set("code.style", "chained")
    ventas, clientes = make_frames()
    return Session([RootSpec("ventas", ventas), RootSpec("clientes", clientes)], registry)


@pytest.mark.parametrize("case", list(CASES))
def test_chained_code_reproduces_the_node(case):
    s = chained_session()
    try:
        ids = []
        for op in CASES[case]:
            ids.append(s.apply(_resolve(op, ids)).id)
        value, script, name = s.wait(ids[-1]), s.code(ids[-1]), s.node(ids[-1]).name
    finally:
        s.close()
    ventas, clientes = make_frames()
    namespace = {"ventas": ventas, "clientes": clientes}
    exec(script, namespace)  # noqa: S102 - framelab-generated display code under test
    assert_same(value, namespace[name])


def test_a_pipeline_becomes_one_chained_expression():
    s = chained_session()
    try:
        a = s.apply(where("n1", gt(col("monto"), 50)))
        b = s.apply(setcol(a.id, "total", mul(col("monto"), col("cantidad"))))
        c = s.apply(call(b.id, "groupby", by=ref_col("pais")))
        d = s.apply(getitem(c.id, "total"))
        e = s.apply(call(d.id, "sum"))
        f = s.apply(call(e.id, "sort_values", ascending=False), name="ranking")
        assert s.code(f.id) == (
            "import pandas as pd\n\n"
            "# ventas: the DataFrame (6 × 7) passed to fl.explore()\n"
            "ranking = (\n"
            '    ventas.loc[lambda df: df["monto"] > 50]\n'
            '    .assign(total=lambda df: df["monto"] * df["cantidad"])\n'
            '    .groupby(by="pais")["total"]\n'
            "    .sum()\n"
            "    .sort_values(ascending=False)\n"
            ")\n"
        )
    finally:
        s.close()


def test_branch_points_stay_variables_and_arguments_inline():
    s = chained_session()
    try:
        x = s.apply(where("n1", gt(col("monto"), 50)))
        y = s.apply(call(x.id, "head", n=2))
        z = s.apply(call(x.id, "tail", n=2))
        w = s.apply(func("concat", objs=[node(y.id), node(z.id)]), name="extremos")
        code = s.code(w.id)
        assert 'ventas_filt = ventas.loc[lambda df: df["monto"] > 50]' in code
        assert "extremos = pd.concat(objs=[ventas_filt.head(n=2), ventas_filt.tail(n=2)])" in code
    finally:
        s.close()


def test_int_keys_break_the_chain_but_stay_faithful():
    s = chained_session()
    try:
        a = s.apply(call("n1", "head", n=3))
        b = s.apply(setcol(a.id, 5, mul(col("monto"), 2)))
        c = s.apply(call(b.id, "tail", n=1))
        code, value, name = s.code(c.id), s.wait(c.id), s.node(c.id).name
        assert "ventas_head_2 = ventas.head(n=3).copy()" not in code  # a statement, not a chain
    finally:
        s.close()
    namespace = {"ventas": make_frames()[0], "clientes": make_frames()[1]}
    exec(code, namespace)  # noqa: S102
    assert_same(value, namespace[name])
