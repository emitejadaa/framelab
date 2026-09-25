import numpy as np
import pandas as pd
import pytest

from framelab.codegen.render import render_expr
from framelab.naming import RootSpec
from framelab.ops import Op, op_from_json, op_to_json
from framelab.ops.formula import FormulaError, parse_formula
from framelab.session import Session

COLUMNS = ["precio", "costo", "cantidad", "precio unitario", "fecha", "nombre"]


@pytest.fixture
def ventas():
    return pd.DataFrame(
        {
            "precio": [120.0, 80.0, np.nan, 200.0],
            "costo": [100.0, 90.0, 10.0, 150.0],
            "cantidad": [1, 3, 2, 5],
            "precio unitario": [1.5, 2.0, 2.5, 3.0],
            "fecha": pd.to_datetime(["2024-01-05", "2024-02-10", "2023-12-31", "2024-03-01"]),
            "nombre": ["ana", "beto", "caro", "dani"],
        }
    )


@pytest.mark.parametrize(
    ("formula", "code"),
    [
        ("(precio - costo) * cantidad / 100", '(v["precio"] - v["costo"]) * v["cantidad"] / 100'),
        ("precio - (costo - 3)", 'v["precio"] - (v["costo"] - 3)'),
        ("precio + costo + cantidad", 'v["precio"] + v["costo"] + v["cantidad"]'),
        ("precio / (costo * cantidad)", 'v["precio"] / (v["costo"] * v["cantidad"])'),
        ("-precio ** 2", '-(v["precio"] ** 2)'),
        ("(-precio) ** 2", '(-v["precio"]) ** 2'),
        ("precio * -3", 'v["precio"] * (-3)'),
        ("precio // 7 % 3", 'v["precio"] // 7 % 3'),
        ("`precio unitario` * 2", 'v["precio unitario"] * 2'),
        ("round(precio / cantidad, 2)", '(v["precio"] / v["cantidad"]).round(2)'),
        ("sqrt(abs(precio - costo))", 'np.sqrt((v["precio"] - v["costo"]).abs())'),
        ("fillna(precio, 0) * cantidad", 'v["precio"].fillna(0) * v["cantidad"]'),
        ('where(precio > 100, "alto", "bajo")', 'np.where(v["precio"] > 100, "alto", "bajo")'),
        ("maximum(precio, costo)", 'np.maximum(v["precio"], v["costo"])'),
        ("fecha.dt.year", 'v["fecha"].dt.year'),
        ("nombre.str.upper()", 'v["nombre"].str.upper()'),
        ('nombre + " " + nombre', 'v["nombre"] + " " + v["nombre"]'),
        ("(precio > 100) & (cantidad < 4)", '(v["precio"] > 100) & (v["cantidad"] < 4)'),
        ("42", "42"),
    ],
)
def test_formulas_render_as_readable_pandas(formula, code):
    assert render_expr(parse_formula(formula, COLUMNS), {}, "v") == code


@pytest.mark.parametrize(
    "formula",
    [
        "precio +",
        "foo * 2",
        "precio.to_csv('x')",
        "precio.__class__",
        "__import__('os')",
        "open('x')",
        "lambda: 1",
        "precio if costo else 1",
        "round(precio, digits=2)",
        "sqrt(precio, costo)",
        "[precio]",
        "",
    ],
)
def test_bad_or_unsafe_formulas_are_rejected(formula):
    with pytest.raises(FormulaError):
        parse_formula(formula, COLUMNS)


def test_error_points_at_the_problem():
    with pytest.raises(FormulaError) as info:
        parse_formula("precio * foo", COLUMNS)
    assert "foo" in str(info.value) and info.value.offset == 9


def test_non_string_column_labels_resolve_by_their_text():
    expr = parse_formula("`2024` * 2", [2024, "x"])
    assert render_expr(expr, {}, "v") == "v[2024] * 2"


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        (
            "(precio - costo) * cantidad / 100",
            lambda d: (d["precio"] - d["costo"]) * d["cantidad"] / 100,
        ),
        ("-precio ** 2 + costo % 7", lambda d: -(d["precio"] ** 2) + d["costo"] % 7),
        (
            "round(sqrt(abs(precio - costo)), 1)",
            lambda d: np.sqrt((d["precio"] - d["costo"]).abs()).round(1),
        ),
        (
            'where(precio > 100, "alto", "bajo")',
            lambda d: np.where(d["precio"] > 100, "alto", "bajo"),
        ),
        (
            "fecha.dt.year * 100 + fecha.dt.month",
            lambda d: d["fecha"].dt.year * 100 + d["fecha"].dt.month,
        ),
        ("`precio unitario` * cantidad", lambda d: d["precio unitario"] * d["cantidad"]),
        ("7", lambda d: 7),
    ],
)
def test_formula_columns_compute_like_hand_written_pandas(ventas, formula, expected):
    session = Session([RootSpec("ventas", ventas)])
    try:
        op = Op(
            kind="setitem",
            target="n1",
            key="nueva",
            expr=parse_formula(formula, list(ventas.columns)),
        )
        node = session.apply(op_from_json(op_to_json(op)))  # the op survives a JSON round trip
        result = session.wait(node.id, 10)
        want = ventas.copy()
        want["nueva"] = expected(ventas)
        pd.testing.assert_frame_equal(result, want)
        # the code shown to the user reproduces it
        namespace = {"pd": pd, "np": np, "ventas": ventas}
        exec(session.code(node.id, mode="step"), namespace)
        pd.testing.assert_frame_equal(namespace[node.name], want)
        pd.testing.assert_frame_equal(session["ventas"], ventas)  # the parent is untouched
    finally:
        session.close()
