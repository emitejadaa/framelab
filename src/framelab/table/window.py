"""Arrow IPC row windows for the grid (spike S7 encoder v2: per-column plans cached per node)."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import reprlib
import time
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from ..codegen.literals import LiteralError, emit_literal, label_text
from ..errors import FramelabError

__all__ = ["NotTabular", "WindowEncoder", "cell_text", "to_frame"]

CHEAP_STR = {
    int,
    float,
    bool,
    str,
    bytes,
    complex,
    type(None),
    dt.date,
    dt.datetime,
    dt.time,
    dt.timedelta,
    decimal.Decimal,
    pd.Timestamp,
    pd.Timedelta,
    pd.Period,
    pd.Interval,
    type(pd.NaT),
    type(pd.NA),
    np.int8,
    np.int16,
    np.int32,
    np.int64,
    np.uint8,
    np.uint16,
    np.uint32,
    np.uint64,
    np.float16,
    np.float32,
    np.float64,
    np.bool_,
    np.str_,
    np.bytes_,
    np.datetime64,
    np.timedelta64,
    np.complex64,
    np.complex128,
}
_JS_SAFE = 2**53 - 1
_CONTAINERS = {list, tuple, dict, set, frozenset}
COLUMN_BUDGET_S = 0.005

_REPR = reprlib.Repr()
_REPR.maxstring = 80
_REPR.maxother = 80
_REPR.maxlist = _REPR.maxtuple = _REPR.maxdict = _REPR.maxset = 8
_REPR.maxlevel = 2


class NotTabular(FramelabError, TypeError):
    code = "not_tabular"


def cell_text(value: Any) -> str:
    """Bounded text for an arbitrary cell value."""
    if isinstance(value, (pd.DataFrame, pd.Series)):
        return f"<{type(value).__name__} {'×'.join(map(str, value.shape))}>"
    return _REPR.repr(value)


def _label_literal(label: Any) -> str | None:
    try:
        return emit_literal(label)
    except LiteralError:
        return None


def to_frame(obj: Any) -> pd.DataFrame | None:
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, pd.Series):
        return obj.to_frame()
    if isinstance(obj, pd.Index):
        return obj.to_frame(index=False)
    return None


def _cheap_types(values: np.ndarray) -> bool:
    return set(map(type, values)) <= CHEAP_STR


def _text_fast(s: pd.Series) -> pa.Array:
    return pa.array(s.astype(str), from_pandas=True)


def _text_bounded(s: pd.Series) -> pa.Array:
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
        if tv in CHEAP_STR or (
            tv in _CONTAINERS
            and len(v) <= 16
            and set(map(type, v.values() if tv is dict else v)) <= CHEAP_STR
        ):
            out[k] = str(v)
        else:
            try:
                out[k] = cell_text(v)
            except Exception as exc:
                out[k] = f"<unprintable {type(v).__name__}: {type(exc).__name__}>"
        if (k & 31) == 31 and time.perf_counter() - t0 > COLUMN_BUDGET_S:
            for j in range(k + 1, len(vals)):
                if not mask[j]:
                    out[j] = f"<{type(vals[j]).__name__}>"
            break
    return pa.array(out, type=pa.string())


def _cat_as_str_dict(s: pd.Series) -> pa.Array:
    codes = s.cat.codes.to_numpy()
    categories = pa.array([str(c) for c in s.cat.categories], type=pa.string())
    return pa.DictionaryArray.from_arrays(pa.array(codes, mask=codes < 0), categories)


def _big_int(arr: pa.Array) -> bool:
    t = arr.type.value_type if pa.types.is_dictionary(arr.type) else arr.type
    if not (pa.types.is_int64(t) or pa.types.is_uint64(t)):
        return False
    a = arr.dictionary if pa.types.is_dictionary(arr.type) else arr
    if a.null_count == len(a):
        return False
    mm = pc.min_max(a)
    return mm["max"].as_py() > _JS_SAFE or mm["min"].as_py() < -_JS_SAFE


def _native(s: pd.Series, type_: pa.DataType | None = None) -> pa.Array:
    arr = pa.array(s, from_pandas=True, type=type_)
    return arr.combine_chunks() if isinstance(arr, pa.ChunkedArray) else arr


Plan = tuple[str, str | None, pa.DataType | None]


def _plan_column(s: pd.Series, js_safe: bool) -> Plan:
    dtype = s.dtype
    if isinstance(dtype, pd.PeriodDtype):
        return "text_fast", None, None
    if isinstance(dtype, pd.SparseDtype):
        return "dense", None, None
    if dtype.kind == "c":
        return "text_fast", "complex has no Arrow type", None
    try:
        arr = _native(s)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {str(exc).splitlines()[0][:100]}"
        if isinstance(dtype, pd.CategoricalDtype):
            return "cat_str", None, None
        vals = s.to_numpy(dtype=object)
        return ("text_fast" if _cheap_types(vals) else "text_bounded"), reason, None
    if js_safe:
        t = arr.type.value_type if pa.types.is_dictionary(arr.type) else arr.type
        if pa.types.is_decimal(t):
            return "text_fast", "decimal as text (js_safe)", None
        if _big_int(arr):
            return "text_fast", "int64 beyond 2^53 as text (js_safe)", None
    return "native", None, (arr.type if s.dtype == object else None)


def _convert(s: pd.Series, strategy: str, type_: pa.DataType | None) -> tuple[pa.Array, str]:
    try:
        if strategy == "native":
            try:
                return _native(s, type_), strategy
            except Exception:
                if type_ is None:
                    raise
                return _native(s), strategy
        if strategy == "dense":
            return _native(s.sparse.to_dense()), strategy
        if strategy == "cat_str":
            return _cat_as_str_dict(s), strategy
        if strategy == "text_fast":
            return _text_fast(s), strategy
    except Exception:
        pass
    return _text_bounded(s), "text_bounded"


class WindowEncoder:
    """One per node: caches a conversion plan per column and reuses it for every window."""

    def __init__(self, frame: pd.DataFrame, *, js_safe: bool = False, include_index: bool = True):
        self.frame = frame
        self.js_safe = js_safe
        self.include_index = include_index
        self._plans: dict[tuple[str, int], Plan] = {}

    def _series(self, win: pd.DataFrame, col_start: int):
        out = []
        if self.include_index:
            idx = win.index
            levels = (
                [idx.get_level_values(k) for k in range(idx.nlevels)]
                if isinstance(idx, pd.MultiIndex)
                else [idx]
            )
            for k, level in enumerate(levels):
                out.append((("i", k), pd.Series(level, copy=False), level.name))
        for j, (label, s) in enumerate(win.items()):
            out.append((("c", col_start + j), s, label))
        return out

    def encode(
        self, offset: int = 0, limit: int = 1000, col_start: int = 0, col_stop: int | None = None
    ) -> tuple[bytes, dict]:
        offset = max(0, int(offset))
        win = self.frame.iloc[offset : offset + max(0, int(limit)), col_start:col_stop]
        arrays, fields, cols, index = [], [], [], []
        for key, s, label in self._series(win, col_start):
            plan = self._plans.get(key)
            if plan is None:
                plan = self._plans[key] = _plan_column(s, self.js_safe)
            arr, used = _convert(s, plan[0], plan[2])
            if used != plan[0]:
                reason = plan[1] or "planned strategy failed on a later window"
                plan = self._plans[key] = (used, reason, None)
            arrays.append(arr)
            fields.append(pa.field(f"{key[0]}{key[1]}", arr.type))
            unnamed_index = label is None and key[0] == "i"
            entry = {
                "text": None if unnamed_index else label_text(label),
                "literal": None if unnamed_index else _label_literal(label),
                "dtype": str(s.dtype),
                "strategy": used,
                "fallback": plan[1] if used in ("text_fast", "text_bounded") else None,
            }
            (index if key[0] == "i" else cols).append(entry)
        meta = {
            "offset": offset,
            "nrows_total": int(len(self.frame)),
            "ncols_total": int(self.frame.shape[1]),
            "col_start": col_start,
            "column_nlevels": int(win.columns.nlevels),
            "columns": cols,
            "index": index,
        }
        schema = pa.schema(fields, metadata={"framelab": json.dumps(meta, ensure_ascii=False)})
        batch = pa.RecordBatch.from_arrays(arrays, schema=schema)
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, schema) as writer:
            writer.write_batch(batch)
        return sink.getvalue().to_pybytes(), meta
