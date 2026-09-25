import pytest

from framelab.naming import auto_node_name
from framelab.ops.build import (
    attr,
    call,
    col,
    func,
    getitem,
    gt,
    method,
    node,
    ref_col,
    setcol,
    where,
)

NAMES = {"n1": "ventas", "n2": "clientes", "n3": "ventas_by_mes", "n4": "ventas_head"}


@pytest.mark.parametrize(
    ("op", "name"),
    [
        (call("n1", "head", n=5), "ventas_head_2"),
        (call("n1", "sort_values", by=ref_col("monto")), "ventas_sorted"),
        (call("n1", "groupby", by=ref_col("mes")), "ventas_by_mes_2"),
        (call("n1", "groupby", by=[ref_col("año"), ref_col("mes")]), "ventas_by_año"),
        (call("n1", "merge", node("n2"), on="id"), "ventas_clientes"),
        (getitem("n1", "precio unitario"), "ventas_precio_unitario"),
        (getitem("n1", 2024), "ventas_2024"),
        (getitem("n1", ["a", "b"]), "ventas_cols"),
        (where("n1", gt(col("monto"), 1)), "ventas_filt"),
        (setcol("n1", "x", method(col("a"), "abs")), "ventas_2"),
        (attr("n1", "T"), "ventas_T"),
        (call("n1", "upper", accessor=("str",)), "ventas_upper"),
        (func("concat", objs=[node("n4"), node("n2")]), "ventas_head_concat"),
    ],
)
def test_auto_names(op, name):
    taken = set(NAMES.values())
    assert auto_node_name(op, NAMES, taken) == name


def test_long_names_keep_the_root_and_the_last_steps():
    names = {"n9": "ventas_filt_2_by_pais_total"}
    trail = ("ventas", "filt", "by_pais", "total")
    got = auto_node_name(call("n9", "sum"), names, set(names.values()), trail)
    assert got == "ventas_total_sum"


def test_very_long_aliases_fall_back_to_root_and_alias():
    names = {"n9": "ventas_" + "x" * 25}
    trail = ("ventas", "x" * 25)
    got = auto_node_name(call("n9", "drop_duplicates"), names, set(names.values()), trail)
    assert got == "ventas_dedup" and len(got) <= 30
