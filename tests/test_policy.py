"""Untrusted op JSON (e.g. a shared .framelab file) must never write files or run code."""

import pandas as pd
import pytest

from framelab.engine import UnsafeCode, run_statement
from framelab.ops import OpError, op_from_json
from framelab.ops.build import call, col, eq, fn, func, method, node, setcol, where


@pytest.mark.parametrize(
    "op",
    [
        call("n1", "to_pickle", "/tmp/x.pkl"),
        call("n1", "to_csv", "/tmp/x.csv"),
        call("n1", "to_parquet", "/tmp/x.parquet"),
        call("n1", "to_sql", "t"),
        call("n1", "eval", "a + 1"),
        call("n1", "query", "a > 1"),
        call("n1", "pipe", fn("sum")),
        call("n1", "plot"),
        call("n1", "update", node("n2")),
        call("n1", "apply", "to_pickle", args=("/tmp/x",)),
        call("n1", "apply", func="to_pickle"),
        call("n1", "agg", func={"a": "to_pickle"}),
        call("n1", "transform", func=fn("to_csv")),
        call("n1", "apply", func=fn("save", "np")),
        call("n1", "apply", func=fn("load", "np")),
        func("read_pickle", node("n1")),
        func("eval", node("n1")),
        where("n1", eq(method(col("a"), "to_pickle", "/tmp/x"), 1)),
        setcol("n1", "b", method(col("a"), "to_csv")),
    ],
)
def test_dangerous_ops_are_rejected(op):
    with pytest.raises(OpError):
        op.validate()


@pytest.mark.parametrize(
    "op",
    [
        call("n1", "to_frame"),
        call("n1", "to_numpy"),
        call("n1", "agg", func={"a": "sum", "b": "mean"}),
        call("n1", "agg", func=fn("mean")),
        call("n1", "transform", func=fn("log1p", "np")),
        call("n1", "apply", func=fn("sqrt", "np")),
        call("n1", "map", arg={"AR": "Argentina"}),
        func("concat", objs=[node("n1"), node("n2")]),
        func("to_datetime", node("n1")),
    ],
)
def test_safe_ops_pass(op):
    op.validate()


def test_untrusted_json_cannot_write_files():
    with pytest.raises(OpError):
        op_from_json(
            {
                "schema_v": 1,
                "kind": "call",
                "target": "n1",
                "name": "to_pickle",
                "args": [{"t": "lit", "v": "/tmp/pwned.pkl"}],
            }
        )


@pytest.mark.parametrize(
    "code",
    [
        'out = pd.read_pickle("x")',
        "out = pd.io.pickle.read_pickle",
        'out = np.load("x")',
        "out = np.lib",
        'out = ventas.to_pickle("x")',
        'out = ventas["a"].to_csv()',
        "out = datetime.datetime",
        "out = decimal.getcontext()",
    ],
)
def test_executor_blocks_module_escapes_and_denied_methods(code):
    with pytest.raises(UnsafeCode):
        run_statement(code, "out", {"ventas": pd.DataFrame({"a": [1]})})


def test_executor_allows_literal_constructors_and_allowed_functions():
    env = {"ventas": pd.DataFrame({"a": [1.0]})}
    code = (
        'out = pd.concat(objs=[ventas, ventas]).assign(t=pd.Timestamp("2024-01-01"), '
        'n=np.nan, l=np.log1p(ventas["a"]), d=datetime.date(2024, 1, 1), '
        'm=decimal.Decimal("1.5"))'
    )
    value, _ = run_statement(code, "out", env)
    assert len(value) == 2
