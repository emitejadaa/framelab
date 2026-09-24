import ast
import datetime
import decimal
import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from framelab.codegen.literals import LiteralError, emit_literal, label_text

NS = {"pd": pd, "np": np, "datetime": datetime, "decimal": decimal}


def roundtrip(value):
    code = emit_literal(value)
    ast.parse(code, mode="eval")
    return code, eval(code, dict(NS))  # noqa: S307 - generated literal under test


def same(a, b):
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a):
        return math.isnan(b)
    if isinstance(a, tuple):
        return isinstance(b, tuple) and len(a) == len(b) and all(map(same, a, b))
    return a == b and type(a) is type(b)


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("monto", '"monto"'),
        ("precio unitario", '"precio unitario"'),
        ("it's", '"it\'s"'),
        ('say "hi"', "'say \"hi\"'"),
        ("año", '"año"'),
        (3, "3"),
        (-2, "-2"),
        (1.5, "1.5"),
        (True, "True"),
        (None, "None"),
        (float("nan"), "np.nan"),
        (float("inf"), "np.inf"),
        (float("-inf"), "-np.inf"),
        (np.int64(7), "7"),
        (np.float32(0.5), "0.5"),
        (np.bool_(False), "False"),
        (("a", 2024), '("a", 2024)'),
        (("solo",), '("solo",)'),
        (["a", "b"], '["a", "b"]'),
        ({"monto": 0}, '{"monto": 0}'),
        (pd.Timestamp("2024-03-01"), 'pd.Timestamp("2024-03-01T00:00:00")'),
        (pd.Timedelta(days=1), 'pd.Timedelta("P1DT0H0M0S")'),
        (decimal.Decimal("1.10"), 'decimal.Decimal("1.10")'),
        (datetime.date(2024, 1, 2), "datetime.date(2024, 1, 2)"),
        (pd.NaT, "pd.NaT"),
        (pd.NA, "pd.NA"),
    ],
)
def test_known_literals(value, code):
    assert emit_literal(value) == code


def test_tz_aware_timestamp_roundtrips():
    ts = pd.Timestamp("2024-03-01 10:00", tz="America/Argentina/Buenos_Aires")
    _, back = roundtrip(ts)
    assert back == ts and str(back.tz) == str(ts.tz)


def test_period_and_interval_roundtrip():
    for value in (pd.Period("2024-01", freq="M"), pd.Interval(0, 5, closed="left")):
        _, back = roundtrip(value)
        assert back == value


def test_unsupported_values_raise():
    with pytest.raises(LiteralError):
        emit_literal(object())
    with pytest.raises(LiteralError):
        emit_literal(pd.DataFrame())


labels = st.recursive(
    st.one_of(
        st.text(max_size=20),
        st.integers(min_value=-(10**12), max_value=10**12),
        st.floats(allow_nan=True, allow_infinity=True),
        st.booleans(),
        st.none(),
        st.datetimes(
            min_value=datetime.datetime(1700, 1, 1), max_value=datetime.datetime(2200, 1, 1)
        ).map(pd.Timestamp),
    ),
    lambda children: st.tuples(children, children),
    max_leaves=4,
)


@given(labels)
def test_any_label_roundtrips(value):
    _, back = roundtrip(value)
    assert same(value, back)


@pytest.mark.parametrize(
    ("label", "text"),
    [("monto", "monto"), (2024, "2024"), (("a", 1), "a / 1"), (None, ""), (1.5, "1.5")],
)
def test_label_text(label, text):
    assert label_text(label) == text
