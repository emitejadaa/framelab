"""Cheap summaries for the inspector (never ``memory_usage(deep=True)``)."""

from __future__ import annotations

import reprlib
from typing import Any

import pandas as pd

from ..codegen.literals import label_text
from .window import _label_literal

__all__ = ["summarize"]

_REPR = reprlib.Repr()
_REPR.maxstring = _REPR.maxother = 200


def _columns(frame: pd.DataFrame) -> list[dict[str, Any]]:
    nulls = frame.isna().sum()
    return [
        {
            "text": label_text(label),
            "literal": _label_literal(label),
            "dtype": str(dtype),
            "nulls": int(nulls.iloc[j]),
        }
        for j, (label, dtype) in enumerate(frame.dtypes.items())
    ]


def summarize(obj: Any) -> dict[str, Any]:
    from pandas.api.typing import DataFrameGroupBy, SeriesGroupBy

    if isinstance(obj, pd.DataFrame):
        return {
            "kind": "DataFrame",
            "shape": [int(n) for n in obj.shape],
            "memory_bytes": int(obj.memory_usage(deep=False).sum()),
            "columns": _columns(obj),
        }
    if isinstance(obj, pd.Series):
        return {
            "kind": "Series",
            "shape": [int(len(obj))],
            "memory_bytes": int(obj.memory_usage(deep=False)),
            "columns": _columns(obj.to_frame()),
        }
    if isinstance(obj, (DataFrameGroupBy, SeriesGroupBy)):
        keys = getattr(obj, "keys", None)  # the `by` argument; not public API, so be defensive
        if keys is None or callable(keys):
            keys = []
        elif not isinstance(keys, list):
            keys = [keys]
        return {
            "kind": "GroupBy",
            "ngroups": int(obj.ngroups),
            "keys": [label_text(k) for k in keys if not hasattr(k, "shape")],
        }
    if isinstance(obj, pd.Index):
        return {"kind": "Index", "shape": [int(len(obj))], "dtype": str(obj.dtype)}
    return {"kind": "Value", "type": type(obj).__name__, "repr": _REPR.repr(obj)}
