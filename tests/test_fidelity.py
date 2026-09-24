"""The code a user copies reproduces the node exactly (spec: 'forma equivalente verificada')."""

import pickle
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from framelab.naming import RootSpec
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
from framelab.session import Session


def make_frames():
    ventas = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5, 6],
            "fecha": pd.to_datetime(
                ["2024-01-03", "2024-01-15", "2024-02-01", "2024-02-20", "2024-03-05", "2024-03-09"]
            ),
            "pais": ["AR", "UY", "AR", None, "BR", "AR"],
            "monto": [120.5, np.nan, 300.0, 45.25, 80.0, 300.0],
            "cantidad": [1, 3, 2, 5, 1, 2],
            "precio unitario": [120.5, 10.0, 150.0, 9.05, 80.0, 150.0],
            "año": [2024] * 6,
        }
    )
    clientes = pd.DataFrame({"id": [1, 2, 3, 7], "nombre": ["Ana", "Beto", "Caro", "Dani"]})
    return ventas, clientes


V = "n1"  # ventas
C = "n2"  # clientes

# Each case: list of ops applied in order (ops may reference earlier results as "@k").
CASES = {
    "head": [call(V, "head", n=3)],
    "tail": [call(V, "tail", n=2)],
    "sample": [call(V, "sample", n=3, random_state=0)],
    "sort desc": [call(V, "sort_values", by=ref_col("monto"), ascending=False)],
    "sort two keys": [call(V, "sort_values", by=[ref_col("pais"), ref_col("monto")])],
    "dedup": [call(V, "drop_duplicates", subset=[ref_col("pais")])],
    "dropna": [call(V, "dropna", subset=[ref_col("monto")])],
    "fillna": [call(V, "fillna", value={"monto": 0.0, "pais": "?"})],
    "rename": [call(V, "rename", columns={"monto": "importe", "precio unitario": "precio"})],
    "drop": [call(V, "drop", columns=[ref_col("cantidad")])],
    "select": [getitem(V, ["pais", "monto"])],
    "column": [getitem(V, "precio unitario")],
    "unicode column": [getitem(V, "año")],
    "filter": [where(V, gt(col("monto"), 100))],
    "filter and": [where(V, and_(eq(col("pais"), "AR"), gt(col("monto"), 100)))],
    "filter or not": [
        where(
            V, or_(method(col("pais"), "isin", ["UY", "BR"]), not_(method(col("monto"), "notna")))
        )
    ],
    "filter empty": [where(V, gt(col("monto"), 10**9))],
    "astype": [call(V, "astype", dtype={"cantidad": "float64"})],
    "describe": [call(V, "describe")],
    "value_counts": [getitem(V, "pais"), call("@0", "value_counts")],
    "groupby sum": [
        call(V, "groupby", by=ref_col("pais")),
        getitem("@0", "monto"),
        call("@1", "sum"),
    ],
    "groupby mean reset": [
        call(V, "groupby", by=ref_col("pais")),
        call("@0", "mean", numeric_only=True),
        call("@1", "reset_index"),
    ],
    "groupby agg func": [
        call(V, "groupby", by=ref_col("pais")),
        getitem("@0", "cantidad"),
        call("@1", "agg", func=fn("max")),
    ],
    "merge": [call(V, "merge", node(C), on="id", how="left")],
    "set upper": [setcol(V, "pais", method(col("pais"), "upper", accessor=("str",)))],
    "set product": [setcol(V, "total", mul(col("monto"), col("cantidad")))],
    "dt year": [getitem(V, "fecha"), attr("@0", "year", accessor=("dt",))],
    "str lower": [getitem(V, "pais"), call("@0", "lower", accessor=("str",))],
    "transpose": [call(V, "head", n=2), attr("@0", "T")],
    "concat": [
        call(V, "head", n=2),
        call(V, "tail", n=2),
        func("concat", objs=[node("@0"), node("@1")]),
    ],
    "scalar": [getitem(V, "monto"), call("@0", "sum")],
    "np function": [getitem(V, "monto"), call("@0", "transform", func=fn("log1p", "np"))],
}


def _resolve(op, ids):
    """Replace "@k" placeholders (k-th op of the case) with real node ids."""
    from dataclasses import replace

    from framelab.ops import op_from_json, op_to_json

    data = op_to_json(op)

    def fix(obj):
        if isinstance(obj, dict):
            return {k: fix(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [fix(v) for v in obj]
        if isinstance(obj, str) and obj.startswith("@"):
            return ids[int(obj[1:])]
        return obj

    return replace(op_from_json(fix(data)))


def run_case(ops):
    ventas, clientes = make_frames()
    before = (ventas.copy(deep=True), clientes.copy(deep=True))
    s = Session([RootSpec("ventas", ventas), RootSpec("clientes", clientes)])
    ids = []
    for op in ops:
        ids.append(s.apply(_resolve(op, ids)).id)
    last = s.node(ids[-1])
    value = s.wait(last.id)
    script = s.code(last.id)
    s.close()
    return value, script, last.name, before


def assert_same(a, b):
    if isinstance(a, pd.DataFrame):
        pd.testing.assert_frame_equal(a, b)
    elif isinstance(a, pd.Series):
        pd.testing.assert_series_equal(a, b)
    elif isinstance(a, pd.Index):
        pd.testing.assert_index_equal(a, b)
    elif isinstance(a, float) and np.isnan(a):
        assert np.isnan(b)
    else:
        assert a == b and type(a) is type(b)


@pytest.mark.parametrize("case", list(CASES))
def test_displayed_code_reproduces_the_node(case):
    value, script, name, before = run_case(CASES[case])
    ventas, clientes = make_frames()
    namespace = {"ventas": ventas, "clientes": clientes}
    exec(script, namespace)  # noqa: S102 - the script under test is framelab-generated
    assert_same(value, namespace[name])
    # neither the session nor the user's script touched the originals
    pd.testing.assert_frame_equal(namespace["ventas"], before[0])
    pd.testing.assert_frame_equal(namespace["clientes"], before[1])


def test_exported_script_runs_in_a_fresh_interpreter(tmp_path):
    ops = [
        where(V, gt(col("monto"), 50)),
        call("@0", "groupby", by=ref_col("pais")),
        getitem("@1", "monto"),
        call("@2", "sum"),
    ]
    value, script, name, _ = run_case(ops)
    ventas, clientes = make_frames()
    ventas.to_pickle(tmp_path / "ventas.pkl")
    clientes.to_pickle(tmp_path / "clientes.pkl")
    out = tmp_path / "out.pkl"
    program = (
        "import pandas as pd\n"
        f"ventas = pd.read_pickle({str(tmp_path / 'ventas.pkl')!r})\n"
        f"clientes = pd.read_pickle({str(tmp_path / 'clientes.pkl')!r})\n"
        f"{script}\n"
        f"pd.to_pickle({name}, {str(out)!r})\n"
    )
    subprocess.run([sys.executable, "-c", program], check=True)
    with open(out, "rb") as fh:
        assert_same(value, pickle.load(fh))
