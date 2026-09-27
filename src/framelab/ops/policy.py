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
    "FUNC_REF",
    "OPAQUE",
    "func_spec_ok",
    "literal_func_spec_ok",
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


# Element-wise helpers that are not ufuncs.
NP_ELEMENTWISE = frozenset({"where"})


def np_func_allowed(name: str) -> bool:
    return (
        isinstance(getattr(np, name, None), np.ufunc)
        or name in NP_REDUCTIONS
        or name in NP_ELEMENTWISE
    )


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


# Options of agg/aggregate that are not named aggregations (their strings are not functions).
AGG_OPTIONS = frozenset(
    {"axis", "engine", "engine_kwargs", "numeric_only", "min_count", "skipna", "ddof", "dropna"}
)


class _Opaque:
    """A value only known at run time (an expression, a column, a node): never a safe spec."""


class _FuncRef:
    """A function passed by reference (``np.log``, a checked kernel name)."""


OPAQUE, FUNC_REF = _Opaque(), _FuncRef()


def _spec_ok(value: Any, dict_values: bool) -> bool:
    if value is OPAQUE:
        return False
    if isinstance(value, str):
        return value in ALLOWED_STR_FUNCS
    if isinstance(value, (list, tuple)):
        return all(_spec_ok(v, dict_values) for v in value)
    if isinstance(value, dict):
        return dict_values and all(_spec_ok(v, dict_values) for v in value.values())
    return True  # numbers, None, FUNC_REF


def _named_ok(value: Any) -> bool:
    """A named aggregation value: ``("column", func)`` or a bare ``func``."""
    if isinstance(value, tuple) and len(value) == 2 and value[0] is not OPAQUE:
        return _spec_ok(value[1], True)
    return _spec_ok(value, True)


def literal_func_spec_ok(
    name: str, first: Any, func_kwarg: Any, other_kwargs: dict[str, Any]
) -> bool:
    """Whether the function specs given to apply/agg/aggregate/transform only name pandas
    kernels. Specs are plain values where ``OPAQUE`` marks anything computed at run time.

    ``first`` is the first positional argument, ``func_kwarg`` the ``func=`` keyword (``None``
    when absent) and ``other_kwargs`` the other keywords (named aggregations for agg).
    """
    if name not in FUNC_TAKING:
        return True
    dict_values = name != "apply"
    if not (_spec_ok(first, dict_values) and _spec_ok(func_kwarg, dict_values)):
        return False
    if name in ("agg", "aggregate"):
        return all(_named_ok(v) for k, v in other_kwargs.items() if k not in AGG_OPTIONS)
    return True


def _plain(v: Any) -> Any:
    """An op value as a plain spec: literals as they are, lists/dicts recursively, function
    references as FUNC_REF and everything computed at run time as OPAQUE."""
    from .values import DictV, Func, ListV, Lit

    if isinstance(v, Lit):
        return v.value
    if isinstance(v, Func):
        return FUNC_REF  # checked by check_value
    if isinstance(v, ListV):
        return [_plain(i) for i in v.items]
    if isinstance(v, DictV):
        return {repr(k): _plain(x) for k, x in v.items}
    return OPAQUE


def func_spec_ok(name: str, args: Any, kwargs: Any) -> bool:
    """``literal_func_spec_ok`` for op values (positional ``args``, ``(key, value)`` kwargs)."""
    if name not in FUNC_TAKING:
        return True
    kw = dict(kwargs)
    first = _plain(args[0]) if args else None
    func = _plain(kw.pop("func")) if "func" in kw else None
    return literal_func_spec_ok(name, first, func, {k: _plain(v) for k, v in kw.items()})
