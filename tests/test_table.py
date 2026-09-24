import decimal
import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call, col, gt, ref_col, where
from framelab.session import Session
from framelab.table import WindowEncoder, summarize
from framelab.table.window import NotTabular


def decode(data: bytes) -> tuple[pa.Table, dict]:
    reader = pa.ipc.open_stream(data)
    table = reader.read_all()
    return table, json.loads(table.schema.metadata[b"framelab"])


def test_window_positional_fields_and_labels():
    df = pd.DataFrame({"monto": [1.0, 2.0], ("a", 1): [3, 4], 2024: ["x", "y"], "año": [1, 2]})
    data, meta = WindowEncoder(df).encode(0, 10)
    table, meta2 = decode(data)
    assert meta == meta2
    assert table.column_names == ["i0", "c0", "c1", "c2", "c3"]
    assert [c["text"] for c in meta["columns"]] == ["monto", "a / 1", "2024", "año"]
    assert [c["literal"] for c in meta["columns"]] == ['"monto"', '("a", 1)', "2024", '"año"']
    assert meta["nrows_total"] == 2 and meta["ncols_total"] == 4


def test_messy_columns_fall_back_to_text_with_badge():
    df = pd.DataFrame(
        {
            "mixed": [1, "a", 2.5],
            "lists": [[1, 2], [3], []],
            "dec": [decimal.Decimal("1.1"), decimal.Decimal("2.2"), None],
            "period": pd.period_range("2024-01", periods=3, freq="M"),
            "complex": [1 + 2j, 3j, 0j],
            "nullable": pd.array([1, None, 3], dtype="Int64"),
            "cat": pd.Categorical([1, 2, 1]),
        }
    )
    data, meta = WindowEncoder(df).encode()
    table, _ = decode(data)
    strategies = {c["text"]: c["strategy"] for c in meta["columns"]}
    assert strategies["period"] == "text_fast"
    assert strategies["complex"] == "text_fast"
    assert table.num_rows == 3
    assert meta["columns"][0]["fallback"] is not None  # mixed types forced to text


def test_window_slices_rows_and_columns():
    df = pd.DataFrame(np.arange(60).reshape(10, 6), columns=list("abcdef"))
    data, meta = WindowEncoder(df).encode(offset=8, limit=5, col_start=2, col_stop=4)
    table, _ = decode(data)
    assert table.num_rows == 2 and table.column_names == ["i0", "c2", "c3"]
    assert meta["col_start"] == 2 and [c["text"] for c in meta["columns"]] == ["c", "d"]
    data, meta = WindowEncoder(df).encode(offset=100, limit=5)
    assert decode(data)[0].num_rows == 0 and meta["nrows_total"] == 10


def test_empty_frame_window_and_summary():
    df = pd.DataFrame({"a": pd.Series([], dtype="float64")})
    data, meta = WindowEncoder(df).encode()
    assert decode(data)[0].num_rows == 0
    assert summarize(df)["shape"] == [0, 1]


def test_summary_shapes():
    df = pd.DataFrame({"a": [1.0, None], "b": ["x", None]})
    s = summarize(df)
    assert s["kind"] == "DataFrame" and s["shape"] == [2, 2]
    assert [(c["text"], c["nulls"]) for c in s["columns"]] == [("a", 1), ("b", 1)]
    assert s["memory_bytes"] > 0
    assert summarize(df["a"])["kind"] == "Series"
    assert summarize(df.groupby("b"))["kind"] == "GroupBy"
    assert summarize(3.5) == {"kind": "Value", "type": "float", "repr": "3.5"}


def test_session_window_and_summary():
    df = pd.DataFrame({"pais": ["AR", "UY"], "monto": [1.0, 5.0]})
    s = Session([RootSpec("ventas", df)])
    f = s.apply(where("n1", gt(col("monto"), 2)))
    data, meta = s.window(f.id)
    assert decode(data)[0].num_rows == 1 and meta["nrows_total"] == 1
    assert s.summary(f.id)["shape"] == [1, 2]
    g = s.apply(call("n1", "groupby", by=ref_col("pais")))
    with pytest.raises(NotTabular):
        s.window(g.id)
    s.close()


def test_large_frame_window_is_cheap():
    df = pd.DataFrame(np.zeros((2_000_000, 3)))
    enc = WindowEncoder(df)
    data, meta = enc.encode(offset=1_999_990, limit=100)
    assert decode(data)[0].num_rows == 10 and meta["nrows_total"] == 2_000_000
