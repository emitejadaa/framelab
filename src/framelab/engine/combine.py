"""What combining two tables gives, before combining them (the Combine dialog).

Row counts are exact for every join type (key counts on both sides, as the size guards use);
duplicate keys and key dtypes pandas refuses to merge are reported so the user can fix them first.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from ..codegen.literals import label_text
from .guards import _labels, as_frame, merge_counts

__all__ = ["describe_merge"]

HOWS = ("inner", "left", "right", "outer")
_SAMPLE = 1000  # object columns: values looked at to tell numbers from text


def _family(values: Any) -> str:
    """What pandas compares a merge key as; keys of different families cannot be merged."""
    dtype = values.dtype
    if isinstance(dtype, pd.CategoricalDtype):
        return _family(pd.Series(dtype.categories))
    if pd.api.types.is_bool_dtype(dtype) or pd.api.types.is_numeric_dtype(dtype):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return f"datetime:{getattr(dtype, 'tz', None)}"
    if pd.api.types.is_timedelta64_dtype(dtype):
        return "timedelta"
    if pd.api.types.is_object_dtype(dtype):
        inferred = pd.api.types.infer_dtype(values.dropna()[:_SAMPLE], skipna=True)
        if inferred in ("integer", "floating", "mixed-integer-float", "decimal", "boolean"):
            return "number"
        if inferred in ("datetime", "datetime64", "date"):
            return "datetime:None"
        if inferred == "empty":
            return "any"
    return "text"


def _keys(frame: pd.DataFrame, labels: list[Any], use_index: bool) -> list[tuple[str, Any]]:
    if use_index:
        idx = frame.index
        return [
            (
                label_text(idx.names[k]) if idx.names[k] is not None else "index",
                idx.get_level_values(k),
            )
            for k in range(idx.nlevels)
        ]
    return [(label_text(c), frame[c]) for c in labels]


def _mismatch(left: pd.DataFrame, right: pd.DataFrame, kw: Mapping[str, Any]) -> list[dict]:
    on = _labels(kw.get("on"))
    left_index, right_index = bool(kw.get("left_index")), bool(kw.get("right_index"))
    lk = _keys(left, [] if left_index else _labels(kw.get("left_on")) or on, left_index)
    rk = _keys(right, [] if right_index else _labels(kw.get("right_on")) or on, right_index)
    out = []
    for (ltext, lv), (rtext, rv) in zip(lk, rk, strict=False):
        lf, rf = _family(lv), _family(rv)
        if "any" not in (lf, rf) and lf != rf:
            out.append(
                {
                    "left": ltext,
                    "right": rtext,
                    "left_dtype": str(lv.dtype),
                    "right_dtype": str(rv.dtype),
                }
            )
    return out


def describe_merge(left: Any, right: Any, kw: Mapping[str, Any]) -> dict[str, Any]:
    """Rows and columns per join type, rows with a repeated key on each side, the relation
    (``validate=``) the data has, and key pairs whose dtypes pandas will not merge."""
    lf, rf = as_frame(left), as_frame(right)
    if lf is None or rf is None:
        raise ValueError("combine needs two tables")
    width = lf.shape[1] + rf.shape[1]
    out: dict[str, Any] = {
        "rows": {"cross": len(lf) * len(rf)},
        "columns": {"cross": width},
        "duplicates": None,
        "relation": None,
        "mismatch": [],
    }
    keyed = ("on", "left_on", "right_on", "left_index", "right_index")
    if not any(kw.get(k) for k in keyed):  # pandas' default: the columns both sides have
        common = [c for c in lf.columns if c in set(rf.columns)]
        if not common:
            return out
        kw = {**kw, "on": common}
    out["mismatch"] = _mismatch(lf, rf, kw)
    if out["mismatch"]:
        return out
    counts = merge_counts(lf, rf, kw)
    if counts is None:
        return out
    out["rows"].update(counts.rows())
    out["columns"].update({how: width - counts.shared for how in HOWS})
    out["duplicates"] = {
        "left": int(counts.left[counts.left > 1].sum()),
        "right": int(counts.right[counts.right > 1].sum()),
    }
    left_unique = not out["duplicates"]["left"]
    right_unique = not out["duplicates"]["right"]
    out["relation"] = (
        ("one_to_one" if right_unique else "one_to_many")
        if left_unique
        else ("many_to_one" if right_unique else "many_to_many")
    )
    return out
