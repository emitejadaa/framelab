"""Table actions: sort for viewing only, and filters made from a cell."""

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from framelab.errors import BadRequest
from framelab.naming import RootSpec
from framelab.ops.build import getitem
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher

VENTAS = pd.DataFrame(
    {
        "pais": ["AR", "UY", "AR", None, "BR"],
        "monto": [120.5, np.nan, 3.0, 45.25, 80.0],
        "fecha": pd.to_datetime(
            ["2024-01-03", "2024-01-15", "2024-02-01", "2024-02-20", "2024-03-05"]
        ),
    },
    index=[10, 10, 11, 12, 13],  # duplicated labels: sorting must be positional
)


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS)])
    yield session
    session.close()


def rows(data: bytes, column: str) -> list:
    return pa.ipc.open_stream(data).read_all().column(column).to_pylist()


def test_sorting_is_for_viewing_only(s):
    data, meta = s.window("n1", 0, 10, sort=(1, False))
    assert rows(data, "c1")[:4] == [120.5, 80.0, 45.25, 3.0]
    assert rows(data, "c1")[4] is None  # missing values last
    assert meta["sort"] == {"column": 1, "ascending": False}
    assert len(s) == 1  # no node was created
    data, _ = s.window("n1", 0, 10)
    assert rows(data, "c1")[0] == 120.5 and rows(data, "c1")[1] is None
    with pytest.raises(BadRequest):
        s.window("n1", 0, 10, sort=(9, True))


@pytest.mark.parametrize(
    ("row", "column", "mode", "sort", "expected"),
    [
        (0, 0, "eq", None, VENTAS[VENTAS["pais"] == "AR"]),
        (0, 0, "ne", None, VENTAS[VENTAS["pais"] != "AR"]),
        (3, 0, "eq", None, VENTAS[VENTAS["pais"].isna()]),
        (1, 1, "ne", None, VENTAS[VENTAS["monto"].notna()]),
        (0, 1, "eq", (1, False), VENTAS[VENTAS["monto"] == 120.5]),
        (2, 2, "eq", None, VENTAS[VENTAS["fecha"] == pd.Timestamp("2024-02-01")]),
    ],
)
def test_filters_from_a_cell_are_faithful(s, row, column, mode, sort, expected):
    node = s.filter_cell("n1", row, column, mode, sort=sort)
    value = s.wait(node.id)
    pd.testing.assert_frame_equal(value, expected)
    namespace = {"ventas": VENTAS.copy()}
    exec(s.code(node.id), namespace)  # noqa: S102 - framelab-generated code
    pd.testing.assert_frame_equal(namespace[node.name], expected)


def test_series_cells_filter_the_series(s):
    monto = s.apply(getitem("n1", "monto"))
    node = s.filter_cell(monto.id, 2, 0, "eq")
    pd.testing.assert_series_equal(s.wait(node.id), VENTAS["monto"][VENTAS["monto"] == 3.0])
    assert "ventas_monto[ventas_monto == 3.0]" in s.code(node.id)


def test_protocol(s):
    d = Dispatcher(s)
    req = {"v": 1, "id": "1", "type": "req"}
    env, bufs = d.handle(
        {
            **req,
            "method": "node.window",
            "params": {"id": "n1", "sort": {"column": 0, "ascending": True}},
        },
        [],
    )
    assert env["result"]["sort"] == {"column": 0, "ascending": True} and bufs
    env, _ = d.handle(
        {**req, "method": "table.filter_cell", "params": {"id": "n1", "row": 0, "column": 0}}, []
    )
    assert env["result"]["node"]["name"] == "ventas_filt"
    env, _ = d.handle(
        {**req, "method": "table.filter_cell", "params": {"id": "n1", "column": 0}}, []
    )
    assert env["error"]["code"] == "bad_request"
