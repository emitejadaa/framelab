"""Guards: refuse operations whose result would not fit in memory, before running them.

Merge row counts are exact (key counts on both sides, spec: "estimación exacta O(n)");
reshaping estimates are exact or slightly high. ``force=True`` skips every guard.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..codegen.literals import label_text
from ..errors import FramelabError
from ..ops import Op
from ..ops.values import Col, ListV, Lit, NodeRef

__all__ = [
    "NUMERIC_AGGS",
    "Estimate",
    "GuardError",
    "MergeCounts",
    "as_frame",
    "check",
    "estimate",
    "merge_counts",
]

NUMERIC_AGGS = frozenset({"sum", "mean", "median", "std", "var", "sem", "prod", "skew", "quantile"})
BYTES_PER_CELL = 8


class GuardError(FramelabError, ValueError):
    code = "too_big"

    def __init__(
        self,
        message: str,
        *,
        kind: str = "size",
        rows: int | None = None,
        nbytes: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind, self.rows, self.nbytes = kind, rows, nbytes
        if kind == "string_aggregation":
            self.code = "string_aggregation"


@dataclass(frozen=True)
class Estimate:
    rows: int
    columns: int

    @property
    def nbytes(self) -> int:
        return self.rows * max(self.columns, 1) * BYTES_PER_CELL


def _plain(v: Any, values: Mapping[str, Any]) -> Any:
    if isinstance(v, Lit):
        return v.value
    if isinstance(v, Col):
        return v.label
    if isinstance(v, NodeRef):
        return values.get(v.id)
    if isinstance(v, ListV):
        return [_plain(i, values) for i in v.items]
    return None


def _labels(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _key_counts(frame: pd.DataFrame, keys: list[Any], use_index: bool) -> pd.Series | None:
    """How many rows have each key (columns, or the index levels)."""
    try:
        if use_index:
            levels = list(range(frame.index.nlevels))
            return frame.groupby(level=levels, dropna=False, observed=True).size()
        return frame.groupby(keys, dropna=False, observed=True).size()
    except (KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MergeCounts:
    """Rows per key on each side of a merge: enough for exact row counts of every ``how``."""

    left: pd.Series
    right: pd.Series
    shared: int  # key columns that come out once (same names on both sides)

    def rows(self) -> dict[str, int]:
        both = pd.concat([self.left.rename("l"), self.right.rename("r")], axis=1).fillna(0)
        inner = int((both["l"] * both["r"]).sum())
        left_only = int(both.loc[both["r"] == 0, "l"].sum())
        right_only = int(both.loc[both["l"] == 0, "r"].sum())
        return {
            "inner": inner,
            "left": inner + left_only,
            "right": inner + right_only,
            "outer": inner + left_only + right_only,
        }


def as_frame(value: Any) -> pd.DataFrame | None:
    if isinstance(value, pd.Series):
        return value.to_frame()
    return value if isinstance(value, pd.DataFrame) else None


def merge_counts(left: Any, right: Any, kw: Mapping[str, Any]) -> MergeCounts | None:
    """Key counts for ``left.merge(right, **kw)`` (keys: ``on``/``left_on``/``right_on``/the
    index); ``None`` when the keys cannot be worked out."""
    left, right = as_frame(left), as_frame(right)
    if left is None or right is None:
        return None
    left_index, right_index = bool(kw.get("left_index")), bool(kw.get("right_index"))
    on = _labels(kw.get("on"))
    lk = [] if left_index else _labels(kw.get("left_on")) or on
    rk = [] if right_index else _labels(kw.get("right_on")) or on
    if not (left_index or right_index or lk or rk):
        lk = rk = [c for c in left.columns if c in set(right.columns)]
    nl = left.index.nlevels if left_index else len(lk)
    nr = right.index.nlevels if right_index else len(rk)
    if not nl or nl != nr:
        return None
    lc, rc = _key_counts(left, lk, left_index), _key_counts(right, rk, right_index)
    if lc is None or rc is None:
        return None
    rc.index = rc.index.set_names(lc.index.names)
    by_name = not (left_index or right_index or kw.get("left_on") or kw.get("right_on"))
    return MergeCounts(lc, rc, len(lk) if by_name else 0)


def _merge(left: Any, right: Any, kw: Mapping[str, Any]) -> Estimate | None:
    lf, rf = as_frame(left), as_frame(right)
    if lf is None or rf is None:
        return None
    how = kw.get("how") or "inner"
    if how == "cross":
        return Estimate(len(lf) * len(rf), lf.shape[1] + rf.shape[1])
    counts = merge_counts(lf, rf, kw)
    rows = None if counts is None else counts.rows().get(how)
    if counts is None or rows is None:
        return None
    return Estimate(rows, lf.shape[1] + rf.shape[1] - counts.shared)


def _join(left: Any, other: Any, kw: Mapping[str, Any]) -> Estimate | None:
    """``left.join(other, on=…)``: ``on`` columns (or the index) against ``other``'s index."""
    on = _labels(kw.get("on"))
    keys: dict[str, Any] = {"how": kw.get("how") or "left", "right_index": True}
    if on:
        keys["left_on"] = on
    else:
        keys["left_index"] = True
    return _merge(left, other, keys)


def _encoded(frame: pd.DataFrame) -> list[Any]:
    return [
        c
        for c, dtype in frame.dtypes.items()
        if pd.api.types.is_object_dtype(dtype)
        or pd.api.types.is_string_dtype(dtype)
        or isinstance(dtype, pd.CategoricalDtype)
    ]


def _get_dummies(data: Any, kw: Mapping[str, Any]) -> Estimate | None:
    dropna = not kw.get("dummy_na", False)
    if isinstance(data, pd.Series):
        return Estimate(len(data), int(data.nunique(dropna=dropna)))
    if not isinstance(data, pd.DataFrame):
        return None
    columns = [c for c in _labels(kw.get("columns")) or _encoded(data) if c in data.columns]
    extra = sum(int(data[c].nunique(dropna=dropna)) for c in columns)
    return Estimate(len(data), data.shape[1] - len(columns) + extra)


def _explode(obj: Any, column: Any) -> Estimate | None:
    if isinstance(obj, pd.Series):
        series, width = obj, 1
    elif isinstance(obj, pd.DataFrame) and column is not None:
        first = _labels(column)[0]
        if first not in obj.columns:
            return None
        series, width = obj[first], obj.shape[1]
    else:
        return None

    def length(x: Any) -> int:
        if pd.api.types.is_list_like(x) and not isinstance(x, (str, bytes)):
            return max(len(x), 1)
        return 1

    return Estimate(int(series.map(length).sum()), width)


def _pivot(frame: Any, kw: Mapping[str, Any]) -> Estimate | None:
    if not isinstance(frame, pd.DataFrame):
        return None
    index, columns = _labels(kw.get("index")), _labels(kw.get("columns"))
    if not index and not columns:
        return None
    try:
        rows = len(frame[index].drop_duplicates()) if index else 1
        cols = len(frame[columns].drop_duplicates()) if columns else 1
    except KeyError:
        return None
    grouping = set(index) | set(columns)
    values = _labels(kw.get("values")) or [c for c in frame.columns if c not in grouping]
    return Estimate(rows, cols * max(len(values), 1))


def _crosstab(index: Any, columns: Any) -> Estimate | None:
    if not isinstance(index, pd.Series) or not isinstance(columns, pd.Series):
        return None
    return Estimate(int(index.nunique()), int(columns.nunique()))


def estimate(op: Op, values: Mapping[str, Any]) -> Estimate | None:
    """The size of ``op``'s result, when framelab knows how to predict it cheaply."""
    kw = {k: _plain(v, values) for k, v in op.kwargs}
    args = [_plain(a, values) for a in op.args]
    target = values.get(op.target) if op.target else None
    first = args[0] if args else None
    if op.kind == "call" and not op.accessor:
        if op.name == "merge":
            return _merge(target, first if args else kw.get("right"), kw)
        if op.name == "join":
            return _join(target, first if args else kw.get("other"), kw)
        if op.name == "explode":
            return _explode(target, first if args else kw.get("column"))
        if op.name == "pivot_table":
            return _pivot(target, kw)
    if op.kind == "func":
        second = args[1] if len(args) > 1 else None
        if op.name == "merge":
            left = first if first is not None else kw.get("left")
            return _merge(left, second if second is not None else kw.get("right"), kw)
        if op.name == "get_dummies":
            return _get_dummies(first if args else kw.get("data"), kw)
        if op.name == "pivot_table":
            return _pivot(first if args else kw.get("data"), kw)
        if op.name == "crosstab":
            columns = second if second is not None else kw.get("columns")
            return _crosstab(first if args else kw.get("index"), columns)
    return None


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _string_aggregation(op: Op, values: Mapping[str, Any]) -> None:
    if op.kind != "call" or op.accessor or op.name not in NUMERIC_AGGS:
        return
    if any(k == "numeric_only" for k, _ in op.kwargs):
        return
    from pandas.api.typing import DataFrameGroupBy

    grouped = values.get(op.target) if op.target else None
    if not isinstance(grouped, DataFrameGroupBy):
        return
    try:
        frame = grouped._obj_with_exclusions  # the columns the aggregation touches (private API)
    except AttributeError:
        return
    text = [
        c
        for c, dtype in frame.dtypes.items()
        if not (
            pd.api.types.is_numeric_dtype(dtype)
            or pd.api.types.is_bool_dtype(dtype)
            or pd.api.types.is_datetime64_any_dtype(dtype)
            or pd.api.types.is_timedelta64_dtype(dtype)
        )
    ]
    if text:
        shown = ", ".join(label_text(c) for c in text[:5])
        raise GuardError(
            f"{op.name}() would also try to combine the text columns {shown}. Add "
            "numeric_only=True or choose the columns first (or run it anyway to combine them).",
            kind="string_aggregation",
        )


def check(op: Op, values: Mapping[str, Any], *, limit_bytes: int) -> None:
    """Raise GuardError when ``op`` should not run as it is."""
    _string_aggregation(op, values)
    est = estimate(op, values)
    if est is not None and est.nbytes > limit_bytes:
        raise GuardError(
            f"the result would have about {est.rows:,} rows × {est.columns} columns "
            f"(~{_human(est.nbytes)}), more than the {_human(limit_bytes)} framelab allows. "
            "Check the keys or filter first, or run it anyway.",
            rows=est.rows,
            nbytes=est.nbytes,
        )
