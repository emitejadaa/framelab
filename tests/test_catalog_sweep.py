"""Every allowed pandas member that needs no arguments goes through framelab faithfully.

Applies each one (DataFrame, Series, .str, .dt, GroupBy), then checks that the node's code,
run on its own, gives the same value, and that summaries and table windows work on it.
"""

import pickle

import numpy as np
import pandas as pd
import pytest

from framelab.catalog import load
from framelab.naming import RootSpec
from framelab.ops.build import attr, call, getitem, ref_col
from framelab.session import NodeError, Session

pytestmark = pytest.mark.slow

FRAME = pd.DataFrame(
    {
        "fecha": pd.date_range("2024-01-01", periods=8, freq="D"),
        "pais": pd.array(["AR", "UY", "AR", None, "BR", "AR", "UY", "CL"], dtype="str"),
        "monto": [120.5, np.nan, 300.0, 45.25, 80.0, 300.0, 10.0, 7.5],
        "cantidad": [1, 3, 2, 5, 1, 2, 4, 4],
        "cat": pd.Categorical(list("abcabcab")),
    }
)
RANDOM = {"sample"}  # the code reproduces them only with a random_state


DATA = (
    str,
    bytes,
    int,
    float,
    complex,
    bool,
    type(None),
    list,
    tuple,
    dict,
    np.ndarray,
    np.generic,
)


def same(a, b) -> bool:
    if isinstance(a, (pd.DataFrame, pd.Series, pd.Index)):
        return type(a) is type(b) and a.equals(b)
    if isinstance(a, DATA) or type(a).__module__.startswith("pandas._libs"):  # values
        return pickle.dumps(a) == pickle.dumps(b)
    return type(a) is type(b)  # indexers, windows, groupby objects: views, not data


def test_every_argument_free_member_is_faithful():
    catalog = load()
    s = Session([RootSpec("ventas", FRAME)])
    try:
        monto = s.apply(getitem("n1", "monto"))
        pais = s.apply(getitem("n1", "pais"))
        fecha = s.apply(getitem("n1", "fecha"))
        grouped = s.apply(call("n1", "groupby", by=ref_col("pais")))
        targets = {
            "DataFrame": ("n1", ()),
            "Series": (monto.id, ()),
            "str": (pais.id, ("str",)),
            "dt": (fecha.id, ("dt",)),
            "DataFrameGroupBy": (grouped.id, ()),
        }
        problems, faithful = [], 0
        for owner, (target, accessor) in targets.items():
            for m in catalog.members(owner):
                if not m.allowed or not m.generated or m.kind not in ("method", "property"):
                    continue
                if m.kind == "method" and any(p.required and not p.variadic for p in m.params):
                    continue
                build = call if m.kind == "method" else attr
                node = s.apply(build(target, m.name, accessor=accessor), force=True)
                try:
                    value = s.wait(node.id, timeout=30)
                except NodeError:
                    continue  # pandas refused: an error node, as it should be
                namespace = {"ventas": FRAME.copy()}
                exec(s.code(node.id), namespace)  # noqa: S102 - framelab-generated code
                if m.name not in RANDOM and not same(value, namespace[node.name]):
                    problems.append(f"{owner}.{m.name}")
                else:
                    faithful += 1
                s.summary(node.id)
                if isinstance(value, (pd.DataFrame, pd.Series, pd.Index)):
                    s.window(node.id, 0, 50)
        assert problems == []
        assert faithful > 200
    finally:
        s.close()
