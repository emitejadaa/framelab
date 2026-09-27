"""Code generation regressions found by the multi-agent review."""

import ast

import pandas as pd
import pytest

from framelab.codegen.query import to_query
from framelab.naming import RootSpec, sanitize_identifier
from framelab.ops import Op
from framelab.ops.build import call, col, eq, gt, mul, setcol, where
from framelab.ops.values import AttrE, GetCol, This
from framelab.options import build_default_registry
from framelab.session import Session


def session(frame, **options):
    registry = build_default_registry()
    for key, value in options.items():
        registry.set(key.replace("__", "."), value)
    return Session([RootSpec("ventas", frame)], registry)


def run(code, frame):
    namespace = {"ventas": frame.copy()}
    exec(code, namespace)  # noqa: S102 - framelab-generated code
    return namespace


def test_chained_export_keeps_variables_figures_draw():
    frame = pd.DataFrame({"a": [1, 5, 10, 20], "b": [3, 4, 5, 6]})
    s = session(frame, code__style="chained")
    try:
        filt = s.apply(where("n1", gt(col("a"), 2)))
        s.wait(s.apply(call(filt.id, "head", n=2)).id)
        fig = s.plots.create(filt.id)
        spec = fig["spec"]
        spec["axes"][0]["layers"] = [{"kind": "line", "source": filt.id, "y": [{"col": "a"}]}]
        s.plots.update(fig["id"], spec)
        script = s.export("py")["text"].replace("plt.show()", "")
        namespace = run("import matplotlib\nmatplotlib.use('Agg')\n" + script, frame)
        assert "ventas_filt" in namespace
    finally:
        s.close()


@pytest.mark.parametrize("label", ["nº", "µg"])
@pytest.mark.parametrize(
    "options",
    [{"code__column_assign": "assign"}, {"code__style": "chained"}],
)
def test_labels_that_change_under_nfkc_are_written_as_strings(label, options):
    frame = pd.DataFrame({"precio": [1.0, 2.0, 3.0], label: [10, 20, 30]})
    s = session(frame, **options)
    try:
        node = s.apply(setcol("n1", label, mul(col("precio"), 2)))
        value = s.wait(node.id)
        namespace = run(s.code(node.id), frame)
        pd.testing.assert_frame_equal(namespace[node.name], value)
    finally:
        s.close()


def test_query_style_falls_back_for_nfkc_labels():
    frame = pd.DataFrame({"no": [100, 0, 0], "nº": [1, 2, 3]})
    s = session(frame, code__filter_style="query")
    try:
        node = s.apply(where("n1", gt(col("nº"), 1)))
        value = s.wait(node.id)
        code = s.code(node.id)
        assert ".query(" not in code
        pd.testing.assert_frame_equal(run(code, frame)[node.name], value)
    finally:
        s.close()


@pytest.mark.parametrize("text", ["a\rb", "a\x0cb", "a\x00b", "a\x85b", "a b"])
def test_query_refuses_control_characters(text):
    assert to_query(eq(col("s"), text)) is None
    assert to_query(gt(col(text), 1)) is None


@pytest.mark.parametrize(
    "label", ["Total\n(EUR)", "Importe\r\nneto", 'x\nprint("RAN FROM HEADER")\n#']
)
def test_exported_headers_stay_comments(label):
    frame = pd.DataFrame({label: [1, 2], "b": [3, 4]})
    s = session(frame)
    try:
        s.wait(s.apply(call("n1", "head", n=1)).id)
        script = s.export("py")["text"]
        tree = ast.parse(script)
        assert not any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) for n in tree.body)
        assert "RAN FROM HEADER" not in "".join(
            line for line in script.splitlines() if not line.startswith("#")
        )
    finally:
        s.close()


def test_assign_style_with_a_method_valued_formula_stays_faithful():
    frame = pd.DataFrame({"precio": [1.0, 2.0]})
    s = session(frame, code__column_assign="assign")
    try:
        node = s.apply(
            Op("setitem", "n1", key="total", expr=AttrE(GetCol(This(), "precio"), "sum"))
        )
        value = s.wait(node.id)
        result = run(s.code(node.id), frame)[node.name]
        assert list(result.columns) == list(value.columns)
    finally:
        s.close()


@pytest.mark.parametrize("name", ["datetime", "decimal"])
def test_module_names_are_reserved(name):
    assert sanitize_identifier(name) == f"df_{name}"
