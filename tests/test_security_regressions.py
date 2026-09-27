"""Regressions from the security review: untrusted documents must not write files or inject code."""

import ast

import pandas as pd
import pytest

from framelab.engine import UnsafeCode, validate_code
from framelab.naming import RootSpec
from framelab.ops import Op, OpError, op_from_json, op_to_json
from framelab.ops.build import call, col, method, setcol
from framelab.ops.formula import FormulaError, parse_formula
from framelab.ops.values import Arith, CallE, DictV, GetCol, ListV, Lit, This
from framelab.session import Session
from framelab.session.document import from_document, to_document

FRAME = pd.DataFrame({"a": [1, 2, 3]})


def untrusted(op: Op) -> Op:
    """The path a .framelab document takes: JSON in, validated op out."""
    return op_from_json(op_to_json(op)).validate()


@pytest.mark.parametrize(
    "op",
    [
        # string function names hidden in an inline method call (finding 0)
        setcol("n1", "b", method(col("a"), "agg", "to_csv")),
        setcol("n1", "b", method(col("a"), "agg", ["to_csv"])),
        setcol("n1", "b", method(col("a"), "transform", {"x": "to_string"})),
        setcol("n1", "b", method(col("a"), "apply", func="to_csv")),
        Op("filter", "n1", expr=CallE(GetCol(This(), "a"), "agg", (), (Lit("to_csv"), Lit(0)))),
        # lists, dicts and named aggregations at the top level (finding 1)
        Op("call", "n1", "agg", (), (ListV((Lit("to_csv"),)), Lit(0), Lit("/tmp/x"))),
        Op("call", "n1", "agg", (), (), (("func", ListV((Lit("to_csv"),))),)),
        Op("call", "n1", "transform", (), (ListV((Lit("to_csv"),)),)),
        Op("call", "n1", "agg", (), (DictV(((Lit("a"), ListV((Lit("to_csv"),))),)),)),
        Op("call", "n1", "agg", (), (), (("x", Lit(("a", "to_string"))),)),
        Op("call", "n1", "agg", (), (), (("x", Lit("to_string")),)),
        # names computed at run time can never be checked, so they are refused
        Op("call", "n1", "agg", (), (Arith(Lit("to_"), "+", Lit("csv")),)),
        Op("call", "n1", "apply", (), (), (("func", GetCol(This(), "a")),)),
        setcol(
            "n1",
            "b",
            CallE(GetCol(This(), "a"), "transform", (), (Arith(Lit("to_"), "+", Lit("csv")),)),
        ),
    ],
)
def test_string_functions_are_checked_everywhere(op):
    with pytest.raises(OpError):
        untrusted(op)


@pytest.mark.parametrize(
    "op",
    [
        call("n1", "agg", ["sum", "mean"]),
        call("n1", "agg", total=("a", "sum")),
        call("n1", "apply", "sum", axis="columns"),
        setcol("n1", "b", method(col("a"), "agg", "sum")),
    ],
)
def test_pandas_kernels_still_pass(op):
    untrusted(op)


def test_formulas_cannot_reach_denied_methods():
    with pytest.raises(FormulaError):
        parse_formula('a.agg("to_csv", 0, "/tmp/x")', ["a"])
    with pytest.raises(FormulaError):
        parse_formula('a.transform(["to_string"])', ["a"])


@pytest.mark.parametrize(
    "code",
    [
        'r = v.agg("to_csv", 0, "/tmp/x")',
        'r = v.agg(["to_csv"])',
        'r = v.transform({"a": "to_pickle"})',
        'r = v.agg(x=("a", "to_string"))',
        'r = v["a"].apply(func="to_csv")',
        'r = v.agg("to_" + "csv")',
        'r = v.agg(v["a"])',
    ],
)
def test_the_executor_refuses_them_too(code):
    with pytest.raises(UnsafeCode):
        validate_code(code, {"v"}, "r")


def test_executor_keeps_allowing_kernels():
    validate_code('r = v.agg(["sum", "mean"], axis="index")', {"v"}, "r")
    validate_code('r = v.agg(total=("a", "sum"))', {"v"}, "r")
    validate_code("r = v.transform(np.log1p)", {"v", "np"}, "r")


def _document(session: Session) -> dict:
    doc = to_document(session)
    return doc


def test_documents_cannot_inject_code_through_source_expr():
    s = Session([RootSpec("ventas", FRAME)])
    try:
        s.wait(s.apply(call("n1", "head", n=2)).id)
        doc = _document(s)
    finally:
        s.close()
    doc["graph"]["nodes"][0]["source"]["source_expr"] = (
        "pd.read_csv('v.csv')\nimport os; os.system('echo PWNED')\nventas"
    )
    restored, problems = from_document(doc, {"ventas": FRAME})
    try:
        assert any("source" in p for p in problems)
        code = restored.code("n2")
        assert "os.system" not in code and "import os" not in code
        ast.parse(code)
    finally:
        restored.close()


def test_simple_source_expressions_survive_documents():
    s = Session([RootSpec("dfs_0", FRAME, "dfs[0]")])
    try:
        doc = _document(s)
    finally:
        s.close()
    restored, problems = from_document(doc, {"dfs_0": FRAME})
    try:
        assert problems == [] and restored.node("n1").source_expr == "dfs[0]"
    finally:
        restored.close()


@pytest.mark.parametrize(
    "exported",
    [
        {"path": "out.png", "dpi": "100)\nimport os\nos.system('echo INJECTED')\nprint(1"},
        {"path": "out.png"},  # missing dpi used to raise KeyError
        {"path": 3, "dpi": 100},
        {"path": "out.png", "dpi": True},
        {"path": "out.png", "dpi": 100, "transparent": "yes"},
    ],
)
def test_documents_cannot_inject_code_through_figure_exports(exported):
    s = Session([RootSpec("ventas", FRAME)])
    try:
        fig = s.plots.create("n1")
        doc = _document(s)
    finally:
        s.close()
    doc["figures"]["items"][0]["exported"] = exported
    restored, problems = from_document(doc, {"ventas": FRAME})
    try:
        assert any("export" in p for p in problems)
        for text in (restored.plots.code(fig["id"]), restored.export("py")["text"]):
            assert "INJECTED" not in text and "savefig" not in text
            ast.parse(text)
    finally:
        restored.close()


def test_valid_figure_exports_survive_documents():
    s = Session([RootSpec("ventas", FRAME)])
    try:
        fig = s.plots.create("n1")
        s.plots.restore("f9", fig["spec"] | {"name": "otra"}, {"path": "o.png", "dpi": 150})
        doc = _document(s)
    finally:
        s.close()
    restored, problems = from_document(doc, {"ventas": FRAME})
    try:
        assert problems == []
        assert 'otra.savefig("o.png", dpi=150)' in restored.plots.code("f9")
    finally:
        restored.close()


def test_root_names_in_documents_must_be_identifiers():
    s = Session([RootSpec("ventas", FRAME)])
    try:
        doc = _document(s)
    finally:
        s.close()
    doc["graph"]["nodes"][0]["name"] = "x = __import__('os')"
    from framelab.session.document import DocumentError

    with pytest.raises(DocumentError):
        from_document(doc, {"x = __import__('os')": FRAME})
