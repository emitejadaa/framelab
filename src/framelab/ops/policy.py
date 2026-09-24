"""What untrusted ops may call. One source of truth for op validation and the executor.

Ops can come from files other people share (``.framelab``), so nothing reachable from an op
may write files, read files, pickle, or evaluate strings. The M1b catalog narrows this further
to an explicit per-class allowlist; this module is the always-on floor.
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = [
    "ALLOWED_PD_FUNCS",
    "ALLOWED_STR_FUNCS",
    "FUNC_TAKING",
    "MODULE_ATTRS",
    "method_allowed",
    "np_func_allowed",
]

# ``to_*`` methods that only convert (no path argument, no side effects).
SAFE_TO = frozenset(
    {
        "to_frame",
        "to_period",
        "to_timestamp",
        "to_numpy",
        "to_dict",
        "to_list",
        "to_records",
        "to_series",
        "to_flat_index",
        "to_pydatetime",
        "to_pytimedelta",
    }
)
# Side effects, string evaluation, arbitrary callables, mutation or plotting state.
DENIED = frozenset(
    {
        "eval",
        "query",
        "pipe",
        "style",
        "plot",
        "hist",
        "boxplot",
        "update",
        "insert",
        "pop",
        "info",
        "iterrows",
        "itertuples",
        "items",
        "memory_usage",
        "set_flags",
        "attrs",
        "flags",
    }
)
# Methods whose string arguments name functions pandas will look up and call.
FUNC_TAKING = frozenset({"apply", "agg", "aggregate", "transform"})

# String function names pandas resolves to its own kernels (spike S6 census).
ALLOWED_STR_FUNCS = frozenset(
    {
        "all",
        "any",
        "count",
        "size",
        "nunique",
        "first",
        "last",
        "min",
        "max",
        "mean",
        "median",
        "sum",
        "prod",
        "std",
        "var",
        "sem",
        "skew",
        "kurt",
        "idxmin",
        "idxmax",
        "quantile",
        "cumsum",
        "cumprod",
        "cummax",
        "cummin",
        "cumcount",
        "rank",
        "diff",
        "pct_change",
        "shift",
        "ffill",
        "bfill",
        "ngroup",
        "describe",
        "value_counts",
        "abs",
        "round",
    }
)
NP_REDUCTIONS = frozenset(
    {
        "sum",
        "mean",
        "median",
        "std",
        "var",
        "min",
        "max",
        "prod",
        "cumsum",
        "cumprod",
        "ptp",
        "nansum",
        "nanmean",
        "nanmedian",
        "nanstd",
        "nanvar",
        "nanmin",
        "nanmax",
        "round",
        "clip",
    }
)
ALLOWED_PD_FUNCS = frozenset(
    {
        "concat",
        "merge",
        "merge_asof",
        "merge_ordered",
        "to_datetime",
        "to_numeric",
        "to_timedelta",
        "cut",
        "qcut",
        "get_dummies",
        "from_dummies",
        "crosstab",
        "melt",
        "pivot",
        "pivot_table",
        "wide_to_long",
        "isna",
        "notna",
        "unique",
        "factorize",
        "date_range",
        "period_range",
        "timedelta_range",
        "interval_range",
    }
)
_LITERAL_CTORS = {"Timestamp", "Timedelta", "Period", "Interval", "NaT", "NA"}


def method_allowed(name: str) -> bool:
    if name in DENIED:
        return False
    return not (name.startswith("to_") and name not in SAFE_TO)


def np_func_allowed(name: str) -> bool:
    return isinstance(getattr(np, name, None), np.ufunc) or name in NP_REDUCTIONS


def _np_attrs() -> frozenset[str]:
    return frozenset({"nan", "inf"} | {n for n in dir(np) if np_func_allowed(n)})


# Attributes the executor lets generated code read from each module name.
MODULE_ATTRS: dict[str, frozenset[str]] = {
    "pd": frozenset(_LITERAL_CTORS | ALLOWED_PD_FUNCS),
    "np": _np_attrs(),
    "datetime": frozenset({"date"}),
    "decimal": frozenset({"Decimal"}),
}


def str_funcs_ok(value: Any, *, dict_values: bool) -> bool:
    """Plain strings (and dict values, for agg-style specs) must be known pandas kernels."""
    if isinstance(value, str):
        return value in ALLOWED_STR_FUNCS
    if isinstance(value, (list, tuple)):
        return all(str_funcs_ok(v, dict_values=dict_values) for v in value)
    if isinstance(value, dict) and dict_values:
        return all(str_funcs_ok(v, dict_values=dict_values) for v in value.values())
    return True
