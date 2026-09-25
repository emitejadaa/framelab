"""Every code style the preferences offer reproduces the node exactly."""

import math

import pytest

from framelab.codegen.query import to_query
from framelab.codegen.style import CodeStyle, import_lines, restyle
from framelab.naming import RootSpec
from framelab.ops.build import and_, call, col, eq, gt, method, mul, not_, or_, setcol, where
from framelab.options import build_default_registry
from framelab.session import Session
from test_fidelity import CASES, _resolve, assert_same, make_frames

STYLES = {
    "query": {"code.filter_style": "query"},
    "assign": {"code.column_assign": "assign"},
    "single+aliases": {
        "code.quote": "single",
        "code.pandas_alias": "pandas",
        "code.numpy_alias": "numpy",
    },
}


def session_with(options, *roots):
    registry = build_default_registry()
    for key, value in options.items():
        registry.set(key, value)
    return Session(list(roots), registry)


def test_restyle_renames_modules_and_quotes():
    code = 'x = pd.Series(np.arange(3))\ny = x.str.replace("a", "b")\nz = df.pd\n# pd stays in comments'
    style = CodeStyle(quote="single", pandas_alias="pandas", numpy_alias="numpy")
    assert restyle(code, style) == (
        "x = pandas.Series(numpy.arange(3))\ny = x.str.replace('a', 'b')\nz = df.pd\n# pd stays in comments"
    )


def test_single_quotes_keep_strings_that_contain_one():
    assert restyle('s = "it\'s"', CodeStyle(quote="single")) == 's = "it\'s"'


def test_import_lines_follow_aliases():
    style = CodeStyle(pandas_alias="pandas")
    assert import_lines({"pd", "np", "plt"}, style) == [
        "import matplotlib.pyplot as plt",
        "import pandas",
        "import numpy as np",
    ]


def test_invalid_or_clashing_aliases_fall_back():
    registry = build_default_registry()
    registry.set("code.pandas_alias", "np")  # would clash with numpy
    assert CodeStyle.from_options(registry).aliases == {"pd": "pd", "np": "np", "plt": "plt"}
    registry.set("code.pandas_alias", "1x")
    assert CodeStyle.from_options(registry).pandas_alias == "pd"
    style = CodeStyle(pandas_alias="pandas")
    assert style.safe_for({"pandas", "ventas"}).pandas_alias == "pd"


@pytest.mark.parametrize(
    ("expr", "query"),
    [
        (gt(col("monto"), 100), "monto > 100"),
        (and_(eq(col("pais"), "AR"), gt(col("monto"), 100)), "pais == 'AR' and monto > 100"),
        (
            or_(and_(eq(col("pais"), "AR"), gt(col("monto"), 100)), not_(eq(col("pais"), "UY"))),
            "(pais == 'AR' and monto > 100) or not (pais == 'UY')",
        ),
        (method(col("pais"), "isin", ["UY", "BR"]), "pais in ['UY', 'BR']"),
        (gt(col("precio unitario"), 3), "`precio unitario` > 3"),
        (gt(col("class"), 3), "`class` > 3"),
        (gt(col("monto"), col("cantidad")), "monto > cantidad"),
        (method(col("monto"), "notna"), None),
        (eq(col("pais"), "it's"), None),
        (gt(col("monto"), math.nan), None),
        (gt(col(2024), 1), None),
    ],
)
def test_to_query(expr, query):
    assert to_query(expr) == query


@pytest.mark.parametrize("style", list(STYLES))
@pytest.mark.parametrize("case", list(CASES))
def test_every_style_reproduces_the_node(style, case):
    ventas, clientes = make_frames()
    s = session_with(STYLES[style], RootSpec("ventas", ventas), RootSpec("clientes", clientes))
    try:
        ids = []
        for op in CASES[case]:
            ids.append(s.apply(_resolve(op, ids)).id)
        value = s.wait(ids[-1])
        script = s.code(ids[-1])
        name = s.node(ids[-1]).name
    finally:
        s.close()
    fresh_ventas, fresh_clientes = make_frames()
    namespace = {"ventas": fresh_ventas, "clientes": fresh_clientes}
    exec(script, namespace)  # noqa: S102 - framelab-generated display code under test
    assert_same(value, namespace[name])


def test_query_and_assign_display_forms():
    ventas, _ = make_frames()
    s = session_with(
        {"code.filter_style": "query", "code.column_assign": "assign"}, RootSpec("ventas", ventas)
    )
    try:
        filt = s.apply(where("n1", and_(eq(col("pais"), "AR"), gt(col("monto"), 100))))
        assert (
            s.code(filt.id, mode="step")
            == "ventas_filt = ventas.query(\"pais == 'AR' and monto > 100\")"
        )
        total = s.apply(setcol("n1", "total", mul(col("monto"), col("cantidad"))))
        assert (
            s.code(total.id, mode="step")
            == 'ventas_2 = ventas.assign(total=ventas["monto"] * ventas["cantidad"])'
        )
        spaced = s.apply(setcol("n1", "precio final", mul(col("monto"), 2)))
        assert 'ventas.assign(**{"precio final": ventas["monto"] * 2})' in s.code(
            spaced.id, mode="step"
        )
        notna = s.apply(where("n1", method(col("monto"), "notna")))
        assert s.code(notna.id, mode="step").startswith("# query() cannot express this condition")
        preview = s.preview(where("n1", gt(col("monto"), 1)))
        assert preview["code"] == 'ventas_filt_3 = ventas.query("monto > 1")'
    finally:
        s.close()


def test_styles_fall_back_on_awkward_labels():
    """Review focus 3: non-string keys, quotes and NaN stay faithful under every style."""
    ventas, _ = make_frames()
    ventas[7] = ventas["cantidad"] * 2
    options = {"code.filter_style": "query", "code.column_assign": "assign", "code.quote": "single"}
    s = session_with(options, RootSpec("ventas", ventas))
    try:
        ops = [
            setcol("n1", 8, mul(col(7), 2)),  # int key: assign(**{8: ...}) is invalid -> copy form
            where("n1", eq(col("pais"), 'O"Neil')),
            where("n1", gt(col("monto"), math.nan)),
            call("n1", "rename", columns={"monto": "it's"}),
        ]
        for op in ops:
            node = s.apply(op)
            value = s.wait(node.id)
            fresh = make_frames()[0]
            fresh[7] = fresh["cantidad"] * 2
            namespace = {"ventas": fresh}
            exec(s.code(node.id), namespace)  # noqa: S102
            assert_same(value, namespace[node.name])
    finally:
        s.close()
