"""What a source offers to the Plotter: mappable fields and a few starting suggestions."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..codegen.literals import label_text
from ..ops.values import OpError, encode_scalar

__all__ = ["field_kind", "fields", "suggestions"]

SAMPLE = 5_000
MAX_CATEGORIES = 40


def field_kind(obj: Any) -> str:
    """num | date | cat | bool | other, as the gallery understands it."""
    dtype = obj.dtype
    if isinstance(obj, pd.MultiIndex):
        return "cat"
    if pd.api.types.is_bool_dtype(dtype):
        return "bool"
    if pd.api.types.is_numeric_dtype(dtype) and not pd.api.types.is_complex_dtype(dtype):
        return "num"
    if pd.api.types.is_datetime64_any_dtype(dtype) or isinstance(dtype, pd.PeriodDtype):
        return "date"
    if (
        isinstance(dtype, (pd.CategoricalDtype, pd.IntervalDtype))
        or pd.api.types.is_string_dtype(dtype)
        or dtype == np.dtype(object)
    ):
        return "cat"
    return "other"


def _describe(ref: dict[str, Any], text: str, obj: Any) -> dict[str, Any]:
    head = obj[:SAMPLE]
    try:
        distinct = int(pd.Series(head).nunique()) if not isinstance(obj, pd.MultiIndex) else None
    except TypeError:
        distinct = None
    return {
        "ref": ref,
        "text": text,
        "dtype": str(obj.dtype),
        "kind": field_kind(obj),
        "distinct": distinct,
    }


def fields(value: Any) -> dict[str, Any]:
    """Index, columns (and values, for a Series) with the kind of data each holds."""
    if isinstance(value, pd.Series):
        name = label_text(value.name) if value.name is not None else ""
        out = [_describe({"values": True}, name, value)]
    elif isinstance(value, pd.DataFrame):
        out = []
        for j, label in enumerate(value.columns):
            try:
                ref = {"col": encode_scalar(label)}
            except OpError:
                continue
            out.append(_describe(ref, label_text(label), value.iloc[:, j]))
    else:
        return {"tabular": False, "rows": 0, "index": None, "fields": []}
    index_name = value.index.name
    index = _describe(
        {"index": True}, label_text(index_name) if index_name is not None else "", value.index
    )
    return {
        "tabular": True,
        "rows": len(value),
        "series": isinstance(value, pd.Series),
        "index": index,
        "fields": out,
    }


def suggestions(value: Any, source: str) -> list[dict[str, Any]]:
    """Up to four layers that make sense for this data (the gallery shows them first)."""
    info = fields(value)
    if not info["tabular"]:
        return []
    cols = info["fields"]
    index = info["index"]
    nums = [f["ref"] for f in cols if f["kind"] == "num"]
    dates = [f["ref"] for f in cols if f["kind"] == "date"]
    cats = [
        f["ref"]
        for f in cols
        if f["kind"] in ("cat", "bool") and f["distinct"] is not None and 1 < f["distinct"] <= 12
    ]
    small = info["rows"] <= MAX_CATEGORIES
    out: list[dict[str, Any]] = []

    def add(kind: str, **fields: Any) -> None:
        if len(out) < 4:
            out.append({"kind": kind, "source": source, **fields})

    if info["series"]:
        if not nums:
            return []
        y = [{"values": True}]
        if index["kind"] == "date":
            add("line", y=y)
        if index["kind"] == "cat" and small:
            add("bar", y=y)
        add("hist", y=y)
        if index["kind"] == "cat" and info["rows"] <= 8:
            add("pie", y=y)
        add("box", y=y)
        return out
    if index["kind"] == "date":
        add("line", y=nums[:3])
    elif dates and nums:
        add("line", x=dates[0], y=nums[:1], **({"hue": cats[0]} if cats else {}))
    if index["kind"] == "cat" and small and nums:
        add("bar", y=nums[:3])
    if len(nums) >= 2:
        add("scatter", x=nums[0], y=[nums[1]], **({"hue": cats[0]} if cats else {}))
    if nums and cats:
        add("box", y=nums[:1], hue=cats[0])
    if nums:
        add("hist", y=nums[:1])
    if nums and len(nums) == len(cols) and info["rows"] <= 60 and len(cols) <= 60:
        add("heatmap")
    return out
