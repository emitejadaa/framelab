"""Encoder v2 (spike s7): per-column strategy chosen once per frame, reused for every window.

Why: v1 (encoder.py) retries pa.array on every window and stringifies failures with a
per-cell Python loop (1-5 ms/column on this CPU). v2:
  * plans each column once (first window), caching the strategy by column position;
  * turns the common "not natively convertible" cases into cheap native Arrow:
      Sparse -> to_dense(); categorical with unconvertible categories -> dictionary<str>;
  * text strategies:
      "text_fast"    pandas 3 ``astype(str)`` (vectorised, keeps NA as null) - used when every
                     cell type has a cheap, bounded ``str`` (scalars, Period, Interval, complex);
      "text_bounded" per-cell bounded formatter (containers, DataFrames, arbitrary objects);
  * int64/uint64 beyond +-2^53 and decimals stay native; the JS side decodes with
    ``{useBigInt: true, useDecimalInt: true}`` (exact).  ``js_safe=True`` instead stringifies them.
Period is always sent as text ("2000-01"): its Arrow form is a bare ordinal.
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
import time
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from encoder import cell_text, label_literal, label_text

CHEAP_STR = {
    int, float, bool, str, bytes, complex, type(None),
    dt.date, dt.datetime, dt.time, dt.timedelta, decimal.Decimal,
    pd.Timestamp, pd.Timedelta, pd.Period, pd.Interval, type(pd.NaT), type(pd.NA),
    np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64,
    np.float16, np.float32, np.float64, np.bool_, np.str_, np.bytes_, np.datetime64, np.timedelta64,
    np.complex64, np.complex128,
}
_JS_SAFE = 2**53 - 1
_CONTAINERS = {list, tuple, dict, set, frozenset}
COLUMN_BUDGET_S = 0.005


def _cheap_types(values: np.ndarray) -> bool:
    return set(map(type, values)) <= CHEAP_STR


def text_fast(s: pd.Series) -> pa.Array:
    return pa.array(s.astype(str), from_pandas=True)


def text_bounded(s: pd.Series) -> pa.Array:
    vals = s.to_numpy(dtype=object)
    try:
        mask = s.isna().to_numpy(dtype=bool, na_value=True)
    except Exception:
        mask = np.zeros(len(vals), dtype=bool)
    out: list[str | None] = [None] * len(vals)
    t0 = time.perf_counter()
    for k in range(len(vals)):
        if mask[k]:
            continue
        v = vals[k]
        tv = type(v)
        if tv in CHEAP_STR:
            out[k] = str(v)
            continue
        if tv in _CONTAINERS and len(v) <= 16 and set(map(type, v.values() if tv is dict else v)) <= CHEAP_STR:
            out[k] = str(v)  # small flat container: C-speed repr, bounded by the length check
            continue
        try:
            out[k] = cell_text(v)
        except Exception as e:
            out[k] = f"<unprintable {type(v).__name__}: {type(e).__name__}>"
        if (k & 31) == 31 and time.perf_counter() - t0 > COLUMN_BUDGET_S:
            for j in range(k + 1, len(vals)):  # budget exhausted: type names only
                if not mask[j]:
                    out[j] = f"<{type(vals[j]).__name__}>"
            break
    return pa.array(out, type=pa.string())


def _cat_as_str_dict(s: pd.Series) -> pa.Array:
    codes = s.cat.codes.to_numpy()
    return pa.DictionaryArray.from_arrays(
        pa.array(codes, mask=codes < 0), pa.array([str(c) for c in s.cat.categories], type=pa.string())
    )


def _big_int(arr: pa.Array) -> bool:
    t = arr.type.value_type if pa.types.is_dictionary(arr.type) else arr.type
    if not (pa.types.is_int64(t) or pa.types.is_uint64(t)):
        return False
    a = arr.dictionary if pa.types.is_dictionary(arr.type) else arr
    if a.null_count == len(a):
        return False
    mm = pc.min_max(a)
    return mm["max"].as_py() > _JS_SAFE or mm["min"].as_py() < -_JS_SAFE


def _native(s: pd.Series, type: pa.DataType | None = None) -> pa.Array:
    arr = pa.array(s, from_pandas=True, type=type)
    return arr.combine_chunks() if isinstance(arr, pa.ChunkedArray) else arr


def plan_column(s: pd.Series, js_safe: bool) -> tuple[str, str | None, pa.DataType | None]:
    """(strategy, reason) for one column, decided on a sample window."""
    dtype = s.dtype
    if isinstance(dtype, pd.PeriodDtype):
        return "text_fast", None, None  # natural text form, not a failure
    if isinstance(dtype, pd.SparseDtype):
        return "dense", None, None
    if dtype.kind == "c":
        return "text_fast", "complex has no Arrow type", None
    try:
        arr = _native(s)
    except Exception as e:
        reason = f"{type(e).__name__}: {str(e).splitlines()[0][:100]}"
        if isinstance(dtype, pd.CategoricalDtype):
            return "cat_str", None, None  # categories shown as text, codes stay native
        vals = s.to_numpy(dtype=object)
        return ("text_fast" if _cheap_types(vals) else "text_bounded"), reason, None
    if js_safe:
        t = arr.type.value_type if pa.types.is_dictionary(arr.type) else arr.type
        if pa.types.is_decimal(t):
            return "text_fast", "decimal as text (js_safe)", None
        if _big_int(arr):
            return "text_fast", "int64 beyond 2^53 as text (js_safe)", None
    # object columns: remember the inferred type (inference dominates their cost)
    return "native", None, (arr.type if s.dtype == object else None)


def convert(s: pd.Series, strategy: str, type: pa.DataType | None = None) -> tuple[pa.Array, str]:
    """Apply a planned strategy; if it fails on this window, degrade (native -> text_bounded)."""
    try:
        if strategy == "native":
            try:
                return _native(s, type), strategy
            except Exception:
                if type is None:
                    raise
                return _native(s), strategy  # this window needs a wider type: re-infer
        if strategy == "dense":
            return _native(s.sparse.to_dense()), strategy
        if strategy == "cat_str":
            return _cat_as_str_dict(s), strategy
        if strategy == "text_fast":
            return text_fast(s), strategy
    except Exception:
        pass
    return text_bounded(s), "text_bounded"


class WindowEncoder:
    """One per root DataFrame (framelab: per session node); caches column plans."""

    def __init__(self, df: pd.DataFrame, *, js_safe: bool = False, include_index: bool = True):
        self.df = df
        self.js_safe = js_safe
        self.include_index = include_index
        self._plans: dict[tuple[str, int], tuple[str, str | None, pa.DataType | None]] = {}

    def _series_list(self, win: pd.DataFrame):
        out = []
        if self.include_index:
            idx = win.index
            levels = [idx.get_level_values(k) for k in range(idx.nlevels)] if isinstance(idx, pd.MultiIndex) else [idx]
            for k, lvl in enumerate(levels):
                out.append((("i", k), pd.Series(lvl, copy=False), lvl.name))
        for j, (label, s) in enumerate(win.items()):
            out.append((("c", j), s, label))
        return out

    def encode(self, offset: int = 0, limit: int = 1000) -> tuple[bytes, dict]:
        win = self.df.iloc[offset : offset + limit]
        arrays, fields, cols, index = [], [], [], []
        for key, s, label in self._series_list(win):
            plan = self._plans.get(key)
            if plan is None:
                plan = self._plans[key] = plan_column(s, self.js_safe)
            arr, used = convert(s, plan[0], plan[2])
            if used != plan[0]:
                self._plans[key] = plan = (used, plan[1] or "planned strategy failed on a later window", None)
            arrays.append(arr)
            fields.append(pa.field(f"{key[0]}{key[1]}", arr.type))
            text = used in ("text_fast", "text_bounded")
            entry = {
                "text": None if label is None and key[0] == "i" else label_text(label),
                "literal": None if label is None and key[0] == "i" else label_literal(label),
                "dtype": str(s.dtype),
                "strategy": used,
                # badge only when the value was forced to text because Arrow could not carry it
                "fallback": plan[1] if text else None,
            }
            (index if key[0] == "i" else cols).append(entry)
        meta = {
            "offset": offset,
            "nrows_total": len(self.df),
            "ncols_total": self.df.shape[1],
            "column_nlevels": win.columns.nlevels,
            "columns": cols,
            "index": index,
        }
        schema = pa.schema(fields, metadata={"framelab": json.dumps(meta, ensure_ascii=False)})
        batch = pa.RecordBatch.from_arrays(arrays, schema=schema)
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, schema) as writer:
            writer.write_batch(batch)
        return sink.getvalue().to_pybytes(), meta


def encode_window(df: pd.DataFrame, offset: int = 0, limit: int = 1000, **kw: Any) -> tuple[bytes, dict]:
    """Stateless convenience (plans every call = cold cost)."""
    return WindowEncoder(df, **kw).encode(offset, limit)
