"""Generate ``src/framelab/catalog/pandas.json.gz`` from the installed pandas.

Run it by hand when the supported pandas version changes (network access the first time):

    .venv/bin/python tools/gen_catalog.py

- categories: pandas' API reference (``doc/source/reference/*.rst`` at the installed version's
  git tag), downloaded once into ``tools/.cache/``;
- parameters: ``inspect.signature`` plus numpydoc type lines (``{'a', 'b'}`` choices);
- return kinds and mutation: probes on a tiny frame (never IO, plotting or string evaluation).
The output is deterministic (sorted keys, gzip mtime 0). Deprecated members are left out.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import gzip
import inspect
import io
import json
import re
import sys
import types
import urllib.request
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from framelab.ops.policy import ALLOWED_PD_FUNCS, method_allowed  # noqa: E402
from framelab.ops.values import OpError, encode_scalar  # noqa: E402

OUT = ROOT / "src" / "framelab" / "catalog" / "pandas.json.gz"
CACHE = ROOT / "tools" / ".cache"
REFERENCE = (
    "https://raw.githubusercontent.com/pandas-dev/pandas/v{version}/doc/source/reference/{page}.rst"
)
PAGES = ("frame", "series", "groupby", "window", "resampling", "indexing", "general_functions")
FORMAT = 1
_HEADINGS = "Parameters|Returns|Yields|Raises|See Also|Notes|Examples|Attributes|Methods"
_SECTION = re.compile(rf"\n\s*(?:{_HEADINGS})\n\s*-{{3,}}")
_UNDERLINE = set("=-~^")


# ---- tiny data and the owners ----------------------------------------------------------------
def tiny() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [1, 2, 3, 4],
            "b": [1.5, 2.5, np.nan, 4.0],
            "s": pd.array(["x", "y", "z", "x"], dtype="str"),
            "t": pd.date_range("2020-01-01", periods=4, freq="D"),
            "c": pd.Categorical(["u", "v", "u", "v"]),
        }
    )


def _frame():
    d = tiny()
    return d, d


def _series():
    s = tiny()["b"].copy()
    return s, s


def _df_groupby():
    d = tiny()[["a", "b", "c"]].copy()
    return d.groupby("c", observed=True), d


def _series_groupby():
    d = tiny()[["a", "b", "c"]].copy()
    return d.groupby("c", observed=True)["b"], d


def _resampler():
    d = tiny()[["a", "b", "t"]].set_index("t")
    return d.resample("2D"), d


def _numeric():
    return tiny()[["a", "b"]].copy()


def _rolling():
    d = _numeric()
    return d.rolling(2), d


def _expanding():
    d = _numeric()
    return d.expanding(), d


def _ewm():
    d = _numeric()
    return d.ewm(com=0.5), d


def _index():
    i = pd.Index(["x", "y", "z", "x"])
    return i, i


def _str():
    s = tiny()["s"].copy()
    return s.str, s


def _dt():
    s = tiny()["t"].copy()
    return s.dt, s


def _cat():
    s = tiny()["c"].copy()
    return s.cat, s


# owner -> (API reference prefix, factory returning (object, what to watch for mutation))
OWNERS: dict[str, tuple[str, Callable[[], tuple[Any, Any]]]] = {
    "DataFrame": ("DataFrame.", _frame),
    "Series": ("Series.", _series),
    "DataFrameGroupBy": ("DataFrameGroupBy.", _df_groupby),
    "SeriesGroupBy": ("SeriesGroupBy.", _series_groupby),
    "Resampler": ("Resampler.", _resampler),
    "Rolling": ("Rolling.", _rolling),
    "Expanding": ("Expanding.", _expanding),
    "ExponentialMovingWindow": ("ExponentialMovingWindow.", _ewm),
    "Index": ("Index.", _index),
    "str": ("Series.str.", _str),
    "dt": ("Series.dt.", _dt),
    "cat": ("Series.cat.", _cat),
}

# Arguments for probing methods that need some (the rest are called with none).
PROBES: dict[str, dict[str, tuple[tuple[Any, ...], dict[str, Any]]]] = {
    "DataFrame": {
        "groupby": ((), {"by": "c", "observed": True}),
        "merge": ((tiny(),), {"on": "a"}),
        "join": ((tiny()[["a"]].rename(columns={"a": "z"}),), {}),
        "sort_values": ((), {"by": "a"}),
        "drop": ((), {"columns": ["a"]}),
        "rename": ((), {"columns": {"a": "x"}}),
        "astype": ((), {"dtype": {"a": "float64"}}),
        "insert": ((0, "z", 1), {}),
        "pop": (("a",), {}),
        "update": ((pd.DataFrame({"a": [9, 9, 9, 9]}),), {}),
        "pivot_table": ((), {"index": "c", "values": "a", "observed": True}),
        "pivot": ((), {"columns": "s", "values": "a"}),
        "set_index": (("a",), {}),
        "apply": ((len,), {}),
        "agg": (("count",), {}),
        "aggregate": (("count",), {}),
        "where": ((tiny().notna(),), {}),
        "mask": ((tiny().isna(),), {}),
        "isin": (([1],), {}),
        "nlargest": ((2, "a"), {}),
        "nsmallest": ((2, "a"), {}),
        "explode": (("a",), {}),
        "select_dtypes": ((), {"include": "number"}),
        "get": (("a",), {}),
        "filter": ((), {"items": ["a"]}),
        "fillna": ((0,), {}),
        "replace": ((1, 2), {}),
        "rolling": ((2,), {}),
        "ewm": ((), {"com": 0.5}),
        "melt": ((), {"id_vars": ["a"], "value_vars": ["b"]}),
        "sample": ((), {"n": 2, "random_state": 0}),
        "assign": ((), {"z": 1}),
        "reindex": ((), {"index": [0, 1]}),
        "set_axis": ((["p", "q", "r", "s", "u"],), {"axis": 1}),
        "combine_first": ((tiny(),), {}),
        "compare": ((tiny().assign(a=[0, 2, 3, 4]),), {}),
        "xs": ((0,), {}),
        "add_prefix": (("p_",), {}),
        "add_suffix": (("_s",), {}),
    },
    "Series": {
        "map": ((str,), {}),
        "apply": ((abs,), {}),
        "astype": (("float64",), {}),
        "isin": (([1.5],), {}),
        "fillna": ((0,), {}),
        "replace": ((1.5, 2.0), {}),
        "where": ((pd.Series([True, False, True, True]),), {}),
        "mask": ((pd.Series([True, False, True, True]),), {}),
        "rolling": ((2,), {}),
        "ewm": ((), {"com": 0.5}),
        "groupby": ((pd.Series(["u", "v", "u", "v"]),), {"observed": True}),
        "nlargest": ((2,), {}),
        "nsmallest": ((2,), {}),
        "between": ((1, 3), {}),
        "clip": ((1, 3), {}),
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "transform": (("abs",), {}),
        "rename": (("z",), {}),
        "sample": ((), {"n": 2, "random_state": 0}),
        "set_axis": (([9, 8, 7, 6],), {}),
        "reindex": (([0, 1],), {}),
        "combine_first": ((pd.Series([0.0, 0.0, 0.0, 0.0]),), {}),
        "compare": ((pd.Series([1.5, 0.0, np.nan, 4.0]),), {}),
        "update": ((pd.Series([9.0]),), {}),
        "get": ((0,), {}),
        "xs": ((0,), {}),
        "add_prefix": (("p_",), {}),
        "add_suffix": (("_s",), {}),
    },
    "DataFrameGroupBy": {
        "get_group": (("u",), {}),
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "transform": (("sum",), {}),
        "apply": ((len,), {}),
        "filter": ((bool,), {}),
        "nth": ((0,), {}),
        "rolling": ((2,), {}),
        "take": (([0],), {}),
    },
    "SeriesGroupBy": {
        "get_group": (("u",), {}),
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "transform": (("sum",), {}),
        "apply": ((len,), {}),
        "filter": ((bool,), {}),
        "nth": ((0,), {}),
        "rolling": ((2,), {}),
        "take": (([0],), {}),
    },
    "Resampler": {
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "transform": (("sum",), {}),
        "apply": (("sum",), {}),
    },
    "Rolling": {
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "apply": ((np.sum,), {"raw": True}),
        "quantile": ((0.5,), {}),
    },
    "Expanding": {
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "apply": ((np.sum,), {"raw": True}),
        "quantile": ((0.5,), {}),
    },
    "Index": {
        "isin": ((["x"],), {}),
        "map": ((str.upper,), {}),
        "astype": (("str",), {}),
        "rename": (("z",), {}),
        "drop": ((["x"],), {}),
        "insert": ((0, "w"), {}),
        "append": ((pd.Index(["q"]),), {}),
        "union": ((pd.Index(["x", "q"]),), {}),
        "intersection": ((pd.Index(["x", "q"]),), {}),
        "difference": ((pd.Index(["x", "q"]),), {}),
        "symmetric_difference": ((pd.Index(["x", "q"]),), {}),
        "get_loc": (("y",), {}),
        "where": ((np.array([True, False, True, True]),), {}),
        "putmask": ((np.array([True, False, False, False]), "q"), {}),
        "set_names": (("n",), {}),
        "fillna": (("q",), {}),
        "equals": ((pd.Index(["x"]),), {}),
        "identical": ((pd.Index(["x"]),), {}),
        "get_indexer": ((["x"],), {}),
        "take": (([0],), {}),
        "repeat": ((2,), {}),
        "delete": ((0,), {}),
    },
    "str": {
        "contains": (("x",), {}),
        "startswith": (("x",), {}),
        "endswith": (("x",), {}),
        "replace": (("x", "y"), {}),
        "pad": ((5,), {}),
        "center": ((5,), {}),
        "ljust": ((5,), {}),
        "rjust": ((5,), {}),
        "zfill": ((5,), {}),
        "repeat": ((2,), {}),
        "get": ((0,), {}),
        "find": (("x",), {}),
        "rfind": (("x",), {}),
        "count": (("x",), {}),
        "match": (("x",), {}),
        "fullmatch": (("x",), {}),
        "extract": ((r"(x)",), {}),
        "extractall": ((r"(x)",), {}),
        "findall": (("x",), {}),
        "wrap": ((2,), {}),
        "join": (("-",), {}),
        "encode": (("utf-8",), {}),
        "translate": (({ord("x"): "y"},), {}),
        "removeprefix": (("x",), {}),
        "removesuffix": (("x",), {}),
        "normalize": (("NFC",), {}),
    },
    "dt": {
        "strftime": (("%Y",), {}),
        "round": (("D",), {}),
        "floor": (("D",), {}),
        "ceil": (("D",), {}),
        "tz_localize": (("UTC",), {}),
        "to_period": (("M",), {}),
        "as_unit": (("s",), {}),
    },
    "cat": {
        "rename_categories": ((["p", "q"],), {}),
        "reorder_categories": ((["v", "u"],), {}),
        "add_categories": ((["w"],), {}),
        "remove_categories": ((["u"],), {}),
        "set_categories": ((["u", "v", "w"],), {}),
    },
}

# Probing runs every other member, policy-denied mutators included (to record ``mutates``).
NEVER_CALL = frozenset(
    {"to_clipboard", "plot", "hist", "boxplot", "style", "info", "pipe", "eval", "query"}
)
SAME_AS_OWNER = frozenset(
    {"add", "sub", "mul", "div", "truediv", "floordiv", "mod", "pow", "radd", "rsub", "rmul",
     "rdiv", "rtruediv", "rfloordiv", "rmod", "rpow", "eq", "ne", "lt", "le", "gt", "ge",
     "combine", "dot"}
)  # fmt: skip
RETURNS = {"resample": "Resampler", "expanding": "Window", "rolling": "Window", "ewm": "Window"}
FUNCTION_RETURNS = {
    "concat": "DataFrame", "merge": "DataFrame", "merge_asof": "DataFrame",
    "merge_ordered": "DataFrame", "to_datetime": "Series", "to_numeric": "Series",
    "to_timedelta": "Series", "cut": "Series", "qcut": "Series", "get_dummies": "DataFrame",
    "from_dummies": "DataFrame", "crosstab": "DataFrame", "melt": "DataFrame",
    "pivot": "DataFrame", "pivot_table": "DataFrame", "wide_to_long": "DataFrame",
    "isna": "Series", "notna": "Series", "unique": "Array", "factorize": "Value",
    "date_range": "Index", "period_range": "Index", "timedelta_range": "Index",
    "interval_range": "Index",
}  # fmt: skip
ROWWISE = frozenset(
    {"head", "tail", "astype", "fillna", "isna", "notna", "isnull", "notnull", "abs", "round",
     "clip", "where", "mask", "replace", "rename", "drop", "assign", "filter", "select_dtypes",
     "copy", "to_frame", "dropna", "between", "isin", "map", "add_prefix", "add_suffix",
     "convert_dtypes", "infer_objects", *SAME_AS_OWNER}
)  # fmt: skip
SAMPLED = frozenset(
    {"describe", "mean", "median", "std", "var", "sum", "min", "max", "count", "nunique",
     "quantile", "sem", "skew", "kurt", "prod", "any", "all"}
)  # fmt: skip

COLUMNS = frozenset({"by", "subset", "on", "left_on", "right_on", "id_vars", "value_vars"})
# Per-member corrections where a parameter name alone does not tell what it holds.
OVERRIDES: dict[tuple[str, str], dict[str, str]] = {
    ("DataFrame", "pivot_table"): {"values": "columns", "index": "columns"},
    ("DataFrame", "pivot"): {"index": "column", "values": "columns"},
    ("DataFrame", "set_index"): {"keys": "columns"},
    ("DataFrame", "explode"): {"column": "columns"},
    ("DataFrame", "melt"): {"var_name": "text", "value_name": "text"},
    ("DataFrame", "duplicated"): {"subset": "columns"},
    ("DataFrame", "value_counts"): {"subset": "columns"},
    ("DataFrameGroupBy", "value_counts"): {"subset": "columns"},
}
FRAMES = frozenset({"other", "right", "objs", "left"})
FREQ = frozenset({"freq", "rule", "offset"})
FUNCS = frozenset({"func", "aggfunc", "arg"})


# ---- the API reference ----------------------------------------------------------------------
def _page(version: str, page: str) -> str:
    path = CACHE / f"pandas-{version}" / f"{page}.rst"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = REFERENCE.format(version=version, page=page)
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed https URL
            path.write_bytes(response.read())
    return path.read_text(encoding="utf-8")


def reference_sections(version: str) -> dict[str, str]:
    """'DataFrame.head' -> 'Indexing, iteration' for every entry of the API reference."""
    out: dict[str, str] = {}
    for page in PAGES:
        lines = _page(version, page).splitlines()
        section, in_summary = page, False
        for i, line in enumerate(lines):
            under = lines[i + 1].strip() if i + 1 < len(lines) else ""
            text = line.strip()
            heading = (
                text
                and not line.startswith(" ")
                and under
                and set(under) <= _UNDERLINE
                and len(under) >= len(text)
            )
            if heading:
                section, in_summary = text.replace("``", ""), False
                continue
            if text.startswith(".. autosummary::"):
                in_summary = True
                continue
            if in_summary:
                if not text or text.startswith(":"):
                    continue
                if not line.startswith("   "):
                    in_summary = False
                    continue
                out.setdefault(text, section)
    return out


# ---- members ----------------------------------------------------------------------------------
def member_doc(raw: Any) -> str:
    wrapped = (getattr(raw, attr, None) for attr in ("fget", "__func__", "_accessor"))
    for obj in (raw, *wrapped):
        doc = getattr(obj, "__doc__", None) if obj is not None else None
        if isinstance(doc, str) and doc.strip():
            return doc
    return ""


def deprecated(doc: str) -> bool:
    head = _SECTION.split(doc, maxsplit=1)[0]
    keyword_note = re.search(r"\.\. deprecated::[^\n]*\n\s*This keyword", head)
    return ".. deprecated::" in head and not keyword_note


def summary(doc: str) -> str:
    para: list[str] = []
    for line in inspect.cleandoc(doc or "").splitlines():
        if not line.strip():
            if para:
                break
            continue
        para.append(line.strip())
    text = " ".join(para)
    return text if len(text) <= 240 else text[:239] + "…"


def member_kind(raw: Any) -> str:
    if isinstance(raw, (classmethod, staticmethod)):
        return "classmethod"
    if type(raw).__name__ in {"Accessor", "CachedAccessor"}:
        return "accessor"
    functions = (
        types.FunctionType,
        types.BuiltinFunctionType,
        types.MethodDescriptorType,
        types.WrapperDescriptorType,
    )
    if isinstance(raw, functions):
        return "method"
    if isinstance(raw, property) or hasattr(type(raw), "__get__"):
        return "property"
    return "method" if callable(raw) else "attribute"


def signature(func: Any) -> inspect.Signature | None:
    try:
        import annotationlib

        return inspect.signature(func, annotation_format=annotationlib.Format.STRING)
    except ImportError:
        pass
    except (TypeError, ValueError):
        return None
    try:
        return inspect.signature(func)
    except (TypeError, ValueError):
        return None


def numpydoc_types(func: Any) -> dict[str, str]:
    try:
        from numpydoc.docscrape import NumpyDocString
    except ImportError:
        return {}
    out: dict[str, str] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            parsed = NumpyDocString(getattr(func, "__doc__", None) or "")
        except Exception:
            return {}
    for p in parsed["Parameters"] + parsed["Other Parameters"]:
        for name in p.name.split(","):
            out[name.strip().lstrip("*")] = p.type
    return out


def choices_of(annotation: str, doc_type: str) -> list[Any]:
    match = re.search(r"Literal\[(.+?)\]", annotation)
    candidates = [match.group(1)] if match else []
    braces = re.search(r"\{([^{}]*)\}", doc_type or "")
    if braces:
        candidates.append(re.sub(r"[`*]", "", braces.group(1)))
    for body in candidates:
        try:
            values = ast.literal_eval(f"[{body}]")
        except (ValueError, SyntaxError):
            continue
        return [v for v in values if isinstance(v, (str, int, float, bool)) or v is None]
    return []


def widget(name: str, annotation: str, default: Any, choices: list[Any]) -> str:
    plain = annotation.replace(" ", "")
    if choices:
        return "choice"
    if name == "axis":
        return "axis"
    if name in COLUMNS:
        return "columns"
    mapping = any(word in annotation for word in ("Renamer", "Mapping", "dict", "Callable"))
    # column labels (drop, nlargest, pivot…), not rename's mapper
    if name == "columns" and not mapping:
        return "columns"
    if name in {"column", "col"}:
        return "column"
    if name in FRAMES:
        return "frame"
    if name == "dtype":
        return "dtype"
    if name in FREQ:
        return "freq"
    if name in FUNCS:
        return "func"
    if isinstance(default, bool) or plain in ("bool", "bool|None", "bool_t"):
        return "bool"
    if isinstance(default, int) or plain in ("int", "int|None"):
        return "int"
    if isinstance(default, float) or plain in ("float", "float|None"):
        return "float"
    if isinstance(default, str) or plain in ("str", "str|None"):
        return "text"
    return "value"


def params_of(func: Any) -> list[dict[str, Any]]:
    sig = signature(func)
    if sig is None:
        return []
    doc_types = numpydoc_types(func)
    out = []
    for p in sig.parameters.values():
        if p.name == "self":
            continue
        if isinstance(p.annotation, str):
            annotation = p.annotation
        elif p.annotation is inspect.Parameter.empty:
            annotation = ""
        else:
            annotation = inspect.formatannotation(p.annotation)
        entry: dict[str, Any] = {"name": p.name, "annotation": annotation}
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            entry.update(variadic="*" if p.kind is p.VAR_POSITIONAL else "**", widget="value")
            out.append(entry)
            continue
        default = None if p.default is p.empty else p.default
        choices = choices_of(annotation, doc_types.get(p.name, ""))
        entry["widget"] = widget(p.name, annotation, default, choices)
        entry["required"] = p.default is p.empty
        if choices:
            entry["choices"] = choices
        if p.default is not p.empty:
            try:
                entry["default"] = encode_scalar(p.default)
            except (OpError, TypeError, ValueError):
                entry["default"] = {"$repr": repr(p.default)[:80]}
        out.append(entry)
    return out


# ---- probes -----------------------------------------------------------------------------------
def returns_kind(value: Any) -> str:
    from pandas.api.typing import (
        DataFrameGroupBy,
        Expanding,
        ExponentialMovingWindow,
        Resampler,
        Rolling,
        SeriesGroupBy,
        Window,
    )

    if value is None:
        return "None"
    for kind, types_ in (
        ("DataFrame", pd.DataFrame),
        ("Series", pd.Series),
        ("Index", pd.Index),
        ("GroupBy", (DataFrameGroupBy, SeriesGroupBy)),
        ("Resampler", Resampler),
        ("Window", (Rolling, Expanding, ExponentialMovingWindow, Window)),
        ("Array", np.ndarray),
    ):
        if isinstance(value, types_):
            return kind
    return "Value"


def unchanged(before: Any, after: Any) -> bool:
    try:
        if isinstance(before, pd.DataFrame):
            return (
                before.columns.equals(after.columns)
                and before.index.equals(after.index)
                and before.dtypes.equals(after.dtypes)
                and before.equals(after)
            )
        if isinstance(before, pd.Series):
            same_index = before.index.equals(after.index)
            return same_index and before.dtype == after.dtype and before.equals(after)
        if isinstance(before, pd.Index):
            return before.dtype == after.dtype and before.equals(after)
    except Exception:
        return False
    return True


def _no_required_args(bound: Any) -> bool:
    sig = signature(bound)
    if sig is None:
        return False
    return all(
        p.default is not p.empty or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        for p in sig.parameters.values()
    )


def probe(owner: str, name: str, kind: str) -> tuple[str, bool]:
    """(return kind, mutates) from running the member on tiny data."""
    writes = name.startswith("to_") and not method_allowed(name)  # IO: never run
    if kind == "classmethod" or writes or name in NEVER_CALL:
        return "unknown", False
    instance, watch = OWNERS[owner][1]()
    before = copy.deepcopy(watch)
    try:
        with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter("ignore")
            if kind != "method":
                value = getattr(instance, name)
            else:
                bound = getattr(instance, name)
                call = PROBES.get(owner, {}).get(name)
                if call is not None:
                    value = bound(*call[0], **call[1])
                elif _no_required_args(bound):
                    value = bound()
                else:
                    return "unknown", False
    except Exception:
        return "unknown", not unchanged(before, watch)
    return returns_kind(value), not unchanged(before, watch)


def preview_policy(owner: str, name: str) -> str:
    if owner in ("str", "dt", "cat") or name in ROWWISE:
        return "rowwise"
    return "sampled_stat" if name in SAMPLED else "global"


def member_entry(
    owner: str, name: str, raw: Any, sections: dict[str, str]
) -> dict[str, Any] | None:
    doc = member_doc(raw)
    if deprecated(doc):
        return None
    prefix = OWNERS[owner][0]
    kind = member_kind(raw)
    entry: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "category": sections.get(prefix + name, "Other"),
        "summary": summary(doc),
        "allowed": method_allowed(name),
        "preview": preview_policy(owner, name),
    }
    if kind in ("method", "classmethod"):
        func = raw.__func__ if isinstance(raw, (classmethod, staticmethod)) else raw
        entry["params"] = params_of(func)
        for param in entry["params"]:
            fixed = OVERRIDES.get((owner, name), {}).get(param["name"])
            if fixed:
                param["widget"] = fixed
    returns, mutates = probe(owner, name, kind)
    if returns == "unknown" and name in SAME_AS_OWNER and owner in ("DataFrame", "Series", "Index"):
        returns = owner
    entry["returns"] = RETURNS.get(name, returns) if returns == "unknown" else returns
    entry["mutates"] = mutates
    return entry


def function_entry(name: str, sections: dict[str, str]) -> dict[str, Any]:
    func = getattr(pd, name)
    doc = func.__doc__ or ""
    return {
        "name": name,
        "kind": "function",
        "category": sections.get(name, "Other"),
        "summary": summary(doc),
        "allowed": True,
        "preview": "global",
        "params": params_of(func),
        "returns": FUNCTION_RETURNS.get(name, "unknown"),
        "mutates": False,
    }


def main() -> None:
    sections = reference_sections(pd.__version__)
    owners: dict[str, Any] = {}
    for owner, (_prefix, factory) in OWNERS.items():
        cls = type(factory()[0])
        members, dropped = [], []
        for name in sorted(dir(cls)):
            if name.startswith("_"):
                continue
            try:
                raw = inspect.getattr_static(cls, name)
            except AttributeError:
                continue
            entry = member_entry(owner, name, raw, sections)
            if entry is None:
                dropped.append(name)
            else:
                members.append(entry)
        owners[owner] = {"members": members, "deprecated": dropped}
    owners["pd"] = {
        "members": [function_entry(n, sections) for n in sorted(ALLOWED_PD_FUNCS)],
        "deprecated": [],
    }
    data = {"format": FORMAT, "pandas_version": pd.__version__, "owners": owners}
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    OUT.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    count = sum(len(o["members"]) for o in owners.values())
    print(f"wrote {OUT.relative_to(ROOT)}: {count} members, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
