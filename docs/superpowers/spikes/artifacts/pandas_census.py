"""THROWAWAY spike s6: pandas 3 introspection census for framelab auto-forms.

Run:  /home/tejada/Desktop/plotExp/.venv/bin/python spikes/s6-pandas-census/census.py

Writes census.json next to this file and prints a markdown summary to stdout.
Not production code: one file, no tests, no API stability.
"""

from __future__ import annotations

import ast
import collections
import collections.abc as cabc
import contextlib
import datetime as _dt
import io
import json
import os
import platform
import re
import sys
import time
import types
import typing
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("MPLBACKEND", "Agg")

import annotationlib  # noqa: E402  (Python 3.14)
import inspect  # noqa: E402

import numpy as np  # noqa: E402
import numpy.typing as npt  # noqa: E402
import pandas as pd  # noqa: E402
import pandas._typing as ptyping  # noqa: E402
from pandas._libs import lib as pdlib  # noqa: E402
from pandas.core.accessor import Accessor  # noqa: E402

try:
    import numpydoc
    from numpydoc.docscrape import NumpyDocString

    NUMPYDOC_VERSION = numpydoc.__version__
except ImportError:  # pragma: no cover
    NumpyDocString = None
    NUMPYDOC_VERSION = None

USE_NUMPYDOC = "--no-numpydoc" not in sys.argv

# ---------------------------------------------------------------------------
# Tiny frame + targets
# ---------------------------------------------------------------------------


def tiny() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [1, 2, 3, 4],
            "b": [1.5, 2.5, np.nan, 4.0],
            "s": pd.array(["x", "y", "z", "x"], dtype="str"),
            "t": pd.date_range("2020-01-01", periods=4, freq="D"),
            "c": pd.Categorical(["u", "v", "u", "v"]),
            "flag": [True, False, True, False],
        }
    )


# (name, factory -> (instance, base_object_for_mutation_check), introspection_instance)
def _targets():
    head0 = tiny().head(0)
    return [
        ("DataFrame", lambda: (lambda d: (d, d))(tiny()), pd.DataFrame),
        ("Series", lambda: (lambda s: (s, s))(tiny()["b"].copy()), pd.Series),
        (
            "DataFrameGroupBy",
            lambda: (lambda d: (d.groupby("c", observed=True), d))(tiny()[["a", "b", "c"]].copy()),
            type(head0.groupby("c", observed=True)),
        ),
        (
            "SeriesGroupBy",
            lambda: (lambda d: (d.groupby("c", observed=True)["b"], d))(tiny()[["a", "b", "c"]].copy()),
            type(head0.groupby("c", observed=True)["b"]),
        ),
        (
            "Resampler",
            lambda: (lambda d: (d.resample("2D"), d))(tiny()[["a", "b", "t"]].set_index("t")),
            type(head0.set_index("t").resample("2D")),
        ),
        (
            "Rolling",
            lambda: (lambda d: (d.rolling(2), d))(tiny()[["a", "b"]].copy()),
            type(head0[["a", "b"]].rolling(2)),
        ),
        (
            "Expanding",
            lambda: (lambda d: (d.expanding(), d))(tiny()[["a", "b"]].copy()),
            type(head0[["a", "b"]].expanding()),
        ),
        (
            "ExponentialMovingWindow",
            lambda: (lambda d: (d.ewm(com=0.5), d))(tiny()[["a", "b"]].copy()),
            type(head0[["a", "b"]].ewm(com=0.5)),
        ),
        ("Index", lambda: (lambda i: (i, i))(pd.Index(["x", "y", "z", "x"])), pd.Index),
        ("str", lambda: (lambda s: (s.str, s))(tiny()["s"].copy()), type(head0["s"].str)),
        ("dt", lambda: (lambda s: (s.dt, s))(tiny()["t"].copy()), type(head0["t"].dt)),
        ("cat", lambda: (lambda s: (s.cat, s))(tiny()["c"].copy()), type(head0["c"].cat)),
    ]


# ---------------------------------------------------------------------------
# Member classification
# ---------------------------------------------------------------------------

PROPERTY_TYPE_NAMES = {"AxisProperty", "CachedProperty", "cache_readonly", "cached_property"}


def classify(raw) -> str:
    if isinstance(raw, (classmethod, staticmethod)):
        return "classmethod-staticmethod"
    if isinstance(raw, Accessor):
        return "accessor"
    if isinstance(raw, (types.FunctionType, types.BuiltinFunctionType, types.MethodDescriptorType)):
        return "method"
    if isinstance(raw, property) or type(raw).__name__ in PROPERTY_TYPE_NAMES:
        return "property"
    if hasattr(type(raw), "__get__") and not callable(raw):
        return "property"
    if hasattr(type(raw), "__set__"):
        return "property"
    if callable(raw):
        # e.g. cython functions, functools.partial objects, wrapper objects
        return "method"
    return "attribute"


_SECTION = re.compile(r"\n\s*(?:Parameters|Returns|Yields|Raises|See Also|Notes|Examples|Attributes|Methods)\n\s*-{3,}")


def member_doc(raw) -> str:
    for obj in (raw, getattr(raw, "fget", None), getattr(raw, "__func__", None), getattr(raw, "_accessor", None)):
        doc = getattr(obj, "__doc__", None) if obj is not None else None
        if isinstance(doc, str) and doc.strip():
            return doc
    return ""


# ---------------------------------------------------------------------------
# Annotation resolution
# ---------------------------------------------------------------------------


def _base_ns() -> dict:
    ns: dict = {}
    ns.update(vars(typing))
    ns.update({k: getattr(cabc, k) for k in cabc.__all__})
    ns.update({k: v for k, v in vars(ptyping).items() if not k.startswith("__")})
    ns.update({k: getattr(pd, k) for k in dir(pd) if not k.startswith("_")})
    import pandas.api.typing as pat

    ns.update({k: getattr(pat, k) for k in dir(pat) if not k.startswith("_")})
    ns.update(
        np=np,
        npt=npt,
        pd=pd,
        lib=pdlib,
        datetime=_dt.datetime,
        date=_dt.date,
        timedelta=_dt.timedelta,
        tzinfo=_dt.tzinfo,
        abc=cabc,
    )
    from pandas._libs.tslibs import BaseOffset, NaTType

    from pandas.core.arrays.base import ExtensionArray
    from pandas.core.dtypes.base import ExtensionDtype
    from pandas.core.generic import NDFrame

    ns.update(BaseOffset=BaseOffset, NaTType=NaTType, ExtensionArray=ExtensionArray, ExtensionDtype=ExtensionDtype, NDFrame=NDFrame)
    return ns


BASE_NS = _base_ns()

# pandas._typing aliases (and a few TYPE_CHECKING names) that map straight to a widget kind
ALIAS_KIND = {
    "Axis": "axis",
    "AxisInt": "axis",
    "Frequency": "freq",
    "TimedeltaConvertibleTypes": "freq",
    "BaseOffset": "freq",
    "DateOffset": "freq",
    "Dtype": "dtype",
    "DtypeArg": "dtype",
    "AstypeArg": "dtype",
    "NpDtype": "dtype",
    "DtypeObj": "dtype",
    "IndexLabel": "labels",
    "Level": "label",
    "Hashable": "label",
    "HashableT": "label",
    "HashableT2": "label",
    "AggFuncType": "func",
    "AggFuncTypeBase": "func",
    "AggFuncTypeDict": "dict",
    "PythonFuncType": "func",
    "ValueKeyFunc": "func",
    "IndexKeyFunc": "func",
    "Renamer": "dict",
    "Scalar": "scalar",
    "PythonScalar": "scalar",
    "TimestampConvertibleTypes": "scalar",
    "DatetimeLikeScalar": "scalar",
    "ListLike": "values",
    "ArrayLike": "values",
    "AnyArrayLike": "values",
    "Axes": "labels",
    "Suffixes": "str",  # 2-tuple of str -> pair of text boxes
    "RandomState": "int",  # seed
    "FilePath": "str",
    "Timezone": "str",
    "NDFrameT": "other-frame",
    "Self": "other-frame",
    "IndexT": "other-frame",
}

UNKNOWN = "unknown"
PRIORITY = [
    "axis",
    "freq",
    "dtype",
    "enum",
    "columns",
    "column",
    "labels",
    "label",
    "other-frame",
    "func",
    "dict",
    "bool",
    "int",
    "float",
    "str",
    "scalar",
    "values",
]
CONCRETE = set(PRIORITY)
CONCRETE_STRICT = CONCRETE - {"scalar", "values"}  # extension kinds not in the brief's list


def _dotted(node) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _lookup(dotted: str, gl: dict):
    parts = dotted.split(".")
    import builtins

    if parts[0] in gl:
        obj = gl[parts[0]]
    elif parts[0] in BASE_NS:
        obj = BASE_NS[parts[0]]
    elif hasattr(builtins, parts[0]):
        obj = getattr(builtins, parts[0])
    else:
        raise NameError(parts[0])
    for p in parts[1:]:
        obj = getattr(obj, p)
    return obj


def parse_ann(text: str, gl: dict, depth: int = 0):
    """Annotation string -> small type tree."""
    if depth > 8:
        return ("opaque", text)
    try:
        tree = ast.parse(text.strip(), mode="eval").body
    except SyntaxError:
        return ("opaque", text)
    return _walk(tree, gl, depth)


def _walk(node, gl, depth):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return ("union", [_walk(node.left, gl, depth), _walk(node.right, gl, depth)])
    if isinstance(node, ast.Constant):
        if node.value is None:
            return ("none",)
        if isinstance(node.value, str):
            return parse_ann(node.value, gl, depth + 1)
        return ("opaque", repr(node.value))
    if isinstance(node, (ast.Name, ast.Attribute)):
        name = _dotted(node)
        short = name.split(".")[-1] if name else None
        if short in ALIAS_KIND:
            return ("alias", short)
        try:
            obj = _lookup(name, gl)
        except Exception:
            return ("opaque", name)
        return from_runtime(obj, gl, depth + 1, name)
    if isinstance(node, ast.Subscript):
        base = _dotted(node.value)
        short = base.split(".")[-1] if base else None
        elts = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if short == "Literal":
            vals = []
            for e in elts:
                try:
                    vals.append(ast.literal_eval(e))
                except Exception:
                    vals.append(ast.unparse(e))
            return ("literal", vals)
        if short == "Optional":
            return ("union", [_walk(elts[0], gl, depth), ("none",)])
        if short == "Union":
            return ("union", [_walk(e, gl, depth) for e in elts])
        if short == "Annotated":
            return _walk(elts[0], gl, depth)
        if short in ALIAS_KIND:
            return ("alias", short)
        try:
            origin = _lookup(base, gl) if base else None
        except Exception:
            origin = None
        oname = getattr(origin, "__name__", short) if origin is not None else short
        args = [_walk(e, gl, depth) for e in elts if not (isinstance(e, ast.Constant) and e.value is Ellipsis)]
        return ("generic", oname, args)
    if isinstance(node, ast.List):  # Callable[[...], R]
        return ("generic", "list", [_walk(e, gl, depth) for e in node.elts])
    return ("opaque", ast.unparse(node))


def from_runtime(t, gl, depth, name=None):
    if depth > 10:
        return ("opaque", repr(t))
    if t is None or t is type(None):
        return ("none",)
    if name and name.split(".")[-1] in ALIAS_KIND:
        return ("alias", name.split(".")[-1])
    if isinstance(t, typing.TypeAliasType):
        return from_runtime(t.__value__, gl, depth + 1, t.__name__)
    if isinstance(t, typing.TypeVar):
        if t.__name__ in ALIAS_KIND:
            return ("alias", t.__name__)
        if t.__bound__ is not None:
            return from_runtime(t.__bound__, gl, depth + 1)
        if t.__constraints__:
            return ("union", [from_runtime(c, gl, depth + 1) for c in t.__constraints__])
        return ("opaque", t.__name__)
    if isinstance(t, typing.ForwardRef):
        return parse_ann(t.__forward_arg__, gl, depth + 1)
    if isinstance(t, str):
        return parse_ann(t, gl, depth + 1)
    if t is typing.Self:
        return ("alias", "Self")
    if t is typing.Any or t is object:
        return ("any",)
    origin = typing.get_origin(t)
    args = typing.get_args(t)
    if origin is typing.Literal:
        return ("literal", list(args))
    if origin in (typing.Union, types.UnionType):
        return ("union", [from_runtime(a, gl, depth + 1) for a in args])
    if origin is typing.Annotated:
        return from_runtime(args[0], gl, depth + 1)
    if origin is not None:
        oname = getattr(origin, "__name__", repr(origin))
        return ("generic", oname, [from_runtime(a, gl, depth + 1) for a in args if a is not Ellipsis])
    if isinstance(t, type):
        return ("class", t)
    return ("opaque", repr(t))


def tree_str(t) -> str:
    k = t[0]
    if k == "union":
        return " | ".join(tree_str(x) for x in t[1])
    if k == "literal":
        return "Literal" + repr(t[1])
    if k == "generic":
        return f"{t[1]}[{', '.join(tree_str(a) for a in t[2])}]"
    if k == "class":
        return t[1].__qualname__
    if k == "alias":
        return "@" + t[1]
    if k == "none":
        return "None"
    if k == "any":
        return "Any"
    return f"?{t[1]}"


def flatten(t):
    if t[0] == "union":
        out = []
        for x in t[1]:
            out.extend(flatten(x))
        return out
    return [t]


SEQ_ORIGINS = {"list", "tuple", "Sequence", "SequenceNotStr", "Iterable", "Collection", "set", "frozenset", "MutableSequence"}
MAP_ORIGINS = {"dict", "Mapping", "MutableMapping", "defaultdict", "OrderedDict"}
FRAME_CLASSES = (pd.DataFrame, pd.Series, pd.Index)


def atom_kind(a) -> tuple[str | None, list | None]:
    """-> (kind or None for 'ignore' atoms, enum choices)."""
    k = a[0]
    if k == "none":
        return None, None
    if k == "alias":
        return ALIAS_KIND[a[1]], None
    if k == "literal":
        vals = [v for v in a[1] if v is not pdlib.no_default and "no_default" not in str(v)]
        if not vals:
            return None, None
        if vals and all(isinstance(v, bool) for v in vals):
            return "bool", None
        return "enum", vals
    if k == "class":
        c = a[1]
        if c is pdlib.NoDefault or c.__name__ in ("NoDefault", "_NoDefault"):
            return None, None
        if issubclass(c, (bool, np.bool_)):
            return "bool", None
        if issubclass(c, (int, np.integer)) or c is typing.SupportsIndex:
            return "int", None
        if issubclass(c, (float, np.floating)):
            return "float", None
        if issubclass(c, str):
            return "str", None
        if issubclass(c, (pd.Timedelta, _dt.timedelta)):
            return "freq", None
        try:
            from pandas._libs.tslibs import BaseOffset

            if issubclass(c, BaseOffset):
                return "freq", None
        except Exception:
            pass
        if issubclass(c, (pd.Timestamp, _dt.datetime, _dt.date, pd.Period, pd.Interval)):
            return "scalar", None
        from pandas.core.generic import NDFrame

        if issubclass(c, FRAME_CLASSES) or issubclass(c, NDFrame):
            return "other-frame", None
        if issubclass(c, (np.dtype,)) or c.__name__ in ("ExtensionDtype",) or issubclass(c, pd.api.extensions.ExtensionDtype):
            return "dtype", None
        if issubclass(c, (np.ndarray, pd.api.extensions.ExtensionArray)):
            return "values", None
        if c in (cabc.Hashable,):
            return "label", None
        if c in (cabc.Callable,) or c.__name__ == "Callable":
            return "func", None
        if issubclass(c, (dict, cabc.Mapping)):
            return "dict", None
        if issubclass(c, (list, tuple, cabc.Sequence)):
            return "values", None
        if c is type:
            return "dtype", None
        return UNKNOWN, None
    if k == "generic":
        o, args = a[1], a[2]
        if o in ("Callable",):
            return "func", None
        if o in MAP_ORIGINS:
            return "dict", None
        if o == "type":
            return "dtype", None
        if o in ("NDArray", "ndarray"):
            return "values", None
        if o in SEQ_ORIGINS:
            inner = [atom_kind(x)[0] for arg in args for x in flatten(arg)]
            inner = [x for x in inner if x]
            if any(x in ("label", "labels", "column", "columns") for x in inner):
                return "labels", None
            if inner and all(x == "str" for x in inner):
                return "values", None
            if inner and all(x == "bool" for x in inner):
                return "bool", None
            if any(x == "other-frame" for x in inner):
                return "other-frame", None
            if any(x == "func" for x in inner):
                return "func", None
            return "values", None
        return UNKNOWN, None
    if k == "any":
        return UNKNOWN, None
    return UNKNOWN, None


def pick(kinds: list[str]) -> str:
    for p in PRIORITY:
        if p in kinds:
            return p
    return UNKNOWN


# ---------------------------------------------------------------------------
# numpydoc fallback
# ---------------------------------------------------------------------------

_BRACES = re.compile(r"\{[^{}]*\}")
NP_TOKENS = [
    (re.compile(r"^(bool|boolean)$"), "bool"),
    (re.compile(r"^(int|integer|int64|non-negative int|positive int)$"), "int"),
    (re.compile(r"^(float|number|numeric)( value)?$"), "float"),
    (re.compile(r"^(str|string)$"), "str"),
    (re.compile(r"^(callable|function|func)$"), "func"),
    (re.compile(r"^(dict|mapping|dict-like|dictionary)"), "dict"),
    (re.compile(r"^(pd\.)?(dataframe|series|index|named series)$"), "other-frame"),
    (re.compile(r"^(column name|column label|column)s?$"), "column"),
    (re.compile(r"^list of (column|col)"), "columns"),
    (re.compile(r"^(list|list-like|sequence|array-like) of (label|hashable|str|string)"), "labels"),
    (re.compile(r"^(label|hashable|level name|index label)$"), "label"),
    (re.compile(r"^labels?$"), "label"),
    (re.compile(r"^(scalar|object)( value)?$"), "scalar"),
    (re.compile(r"^(an? )?(list-like|array-like|list|sequence|ndarray|iterable|tuple|array|index-like|bool array-like|1-d array-like)"), "values"),
    (re.compile(r"^(dtype|type|data type|numpy dtype|str or dtype)"), "dtype"),
    (re.compile(r"^(dateoffset|timedelta|offset|frequency|freq|timedelta string)"), "freq"),
    (re.compile(r"^(timestamp|datetime)"), "scalar"),
]


def parse_np_type(typeline: str):
    """-> (kind, choices) from a numpydoc 'name : <typeline>' type string."""
    t = typeline.strip()
    t = re.sub(r"``([^`]*)``", r"\1", t)
    t = re.sub(r":\w+:`~?([^`]*)`", r"\1", t)
    t = t.replace("`", "").replace('"{', "{").replace('}"', "}")
    m = _BRACES.search(t)
    if m:
        body = m.group(0)
        # axis sets like {0 or 'index', 1 or 'columns'}
        norm = re.sub(r"\s+or\s+", ", ", body)
        try:
            vals = ast.literal_eval(norm)
            if isinstance(vals, (set, dict)):
                vals = list(vals)
            vals = sorted(vals, key=repr)
            if {0, 1} <= set(v for v in vals if isinstance(v, int)) and ("index" in vals or "columns" in vals):
                return "axis", vals
            if vals and all(isinstance(v, bool) for v in vals):
                return "bool", None
            return "enum", vals
        except Exception:
            pass
    # drop default/optional tails
    t2 = re.split(r",?\s*default\b|,?\s*optional\b", t, maxsplit=1)[0]
    toks = [x.strip().strip(".").lower() for x in re.split(r"\bor\b|,|\|", t2) if x.strip()]
    kinds = []
    for tok in toks:
        for rx, kind in NP_TOKENS:
            if rx.search(tok):
                kinds.append(kind)
                break
    if kinds:
        return pick(kinds), None
    return UNKNOWN, None


_NPDOC_CACHE: dict[int, dict] = {}


def npdoc_params(func) -> dict[str, str]:
    if NumpyDocString is None or not USE_NUMPYDOC:
        return {}
    doc = getattr(func, "__doc__", None) or ""
    key = id(doc)
    if key in _NPDOC_CACHE:
        return _NPDOC_CACHE[key]
    out = {}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = NumpyDocString(doc)
        for p in parsed["Parameters"] + parsed["Other Parameters"]:
            for nm in p.name.split(","):
                out[nm.strip().lstrip("*")] = p.type
                if any(".. deprecated::" in line for line in p.desc):
                    out.setdefault("__deprecated__", set()).add(nm.strip().lstrip("*"))
    except Exception:
        pass
    _NPDOC_CACHE[key] = out
    return out


# ---------------------------------------------------------------------------
# Name context / heuristics
# ---------------------------------------------------------------------------

COLUMN_CONTEXT = {"DataFrame", "DataFrameGroupBy", "Resampler", "Rolling", "Expanding", "ExponentialMovingWindow"}
COLUMN_PARAMS = {
    "by",
    "subset",
    "columns",
    "on",
    "left_on",
    "right_on",
    "id_vars",
    "value_vars",
    "values",
    "keys",
    "column",
    "col",
    "cols",
    "include_groups",
}
COLUMN_PARAMS.discard("include_groups")
NAME_KIND = {
    "axis": "axis",
    "freq": "freq",
    "rule": "freq",
    "offset": "freq",
    "func": "func",
    "aggfunc": "func",
    "key": "func",
    "dtype": "dtype",
    "other": "other-frame",
    "right": "other-frame",
    "by": "columns",
    "subset": "columns",
    "columns": "columns",
    "level": "label",
    "name": "label",
    "sep": "str",
    "pat": "str",
    "repl": "str",
}


def widget_for(owner: str, pname: str, ann, gl, default, np_type: str | None):
    """-> dict(widget, source, choices, nullable, candidates, resolved)"""
    resolved = None
    kind, choices, source, candidates, nullable = UNKNOWN, None, None, [], False
    if ann is not inspect.Parameter.empty and ann not in (None, ""):
        tree = parse_ann(ann, gl) if isinstance(ann, str) else from_runtime(ann, gl, 0)
        resolved = tree_str(tree)
        atoms = flatten(tree)
        nullable = any(a[0] == "none" for a in atoms)
        for a in atoms:
            ak, ch = atom_kind(a)
            if ak is None:
                continue
            candidates.append(ak)
            if ch is not None:
                choices = (choices or []) + [c for c in ch if c not in (choices or [])]
        known = [c for c in candidates if c != UNKNOWN]
        if known:
            kind, source = pick(known), "annotation"
    # numpydoc: fallback, or upgrade plain str -> enum when the doc has a {...} set
    if np_type:
        nk, nch = parse_np_type(np_type)
        if kind == UNKNOWN and nk != UNKNOWN:
            kind, choices, source = nk, nch, "numpydoc"
        elif kind in ("str", "scalar", "values") and nk in ("enum", "axis"):
            kind, choices, source = nk, nch, "annotation+numpydoc"
        elif kind == "label" and nk in ("column", "columns"):
            kind, source = nk, "annotation+numpydoc"
    # default value type
    if kind == UNKNOWN and default is not inspect.Parameter.empty and default is not None:
        if isinstance(default, bool):
            kind, source = "bool", "default"
        elif isinstance(default, int):
            kind, source = "int", "default"
        elif isinstance(default, float):
            kind, source = "float", "default"
        elif isinstance(default, str):
            kind, source = "str", "default"
    # column context: label(s) on a column-bearing owner with a column-ish name
    if owner in COLUMN_CONTEXT and pname in COLUMN_PARAMS and kind in ("label", "labels", "values", "str", "scalar"):
        plural = kind in ("labels", "values") or any(c in ("labels", "values") for c in candidates)
        plural = plural or pname in ("columns", "subset", "id_vars", "value_vars")
        kind = "columns" if plural else "column"
        source = (source or "") + "+name"
    # Hashable is also pandas' spelling for "any scalar": fill_value / value / na_rep are values, not labels
    if kind == "label" and (pname.endswith("value") or pname in ("to_replace", "na_rep")):
        kind = "scalar"
        source = (source or "") + "+name"
    # pure name heuristic (last resort)
    if kind == UNKNOWN and pname in NAME_KIND:
        kind, source = NAME_KIND[pname], "name"
    return {
        "widget": kind,
        "source": source,
        "choices": [c if isinstance(c, (str, int, float, bool)) or c is None else repr(c) for c in choices] if choices else None,
        "nullable": nullable,
        "candidates": sorted(set(candidates)),
        "resolved": resolved,
    }


# ---------------------------------------------------------------------------
# Runtime return / mutation probing
# ---------------------------------------------------------------------------


def rkind(x) -> str:
    from pandas.core.groupby.groupby import BaseGroupBy
    from pandas.core.window.rolling import BaseWindow

    if x is None:
        return "None"
    if isinstance(x, pd.DataFrame):
        return "DataFrame"
    if isinstance(x, pd.Series):
        return "Series"
    if isinstance(x, pd.Index):
        return "Index"
    if isinstance(x, BaseGroupBy):
        return "GroupBy/Resampler"
    if isinstance(x, BaseWindow):
        return "Window"
    if isinstance(x, np.ndarray):
        return "ndarray"
    if isinstance(x, pd.api.extensions.ExtensionArray):
        return "ExtensionArray"
    if isinstance(x, str):
        return "str"
    if isinstance(x, (bool, int, float, complex, np.generic, pd.Timestamp, pd.Timedelta, pd.Period, pd.Interval)) or x is pd.NA or x is pd.NaT:
        return "scalar"
    if isinstance(x, bytes):
        return "bytes"
    if isinstance(x, (types.GeneratorType, map, zip, filter)) or (
        isinstance(x, cabc.Iterator) and not isinstance(x, (list, tuple, dict))
    ):
        return "iterator"
    if isinstance(x, (list, tuple, dict, set)):
        return type(x).__name__
    mod = type(x).__module__
    if mod.startswith("matplotlib"):
        return "matplotlib"
    return f"other:{mod}.{type(x).__qualname__}"


PANDAS_KINDS = {"DataFrame", "Series", "Index", "GroupBy/Resampler", "Window"}
NEVER_CALL = {"to_clipboard"}  # touches the system clipboard


def snapshot(base):
    if isinstance(base, (pd.DataFrame, pd.Series)):
        return (base.copy(deep=True), dict(base.attrs), base.flags.allows_duplicate_labels)
    return (base.copy(), None, None)


def changed(base, snap) -> bool:
    copy_, attrs, flags = snap
    try:
        if type(base) is not type(copy_) or base.shape != copy_.shape:
            return True
        if isinstance(base, pd.DataFrame):
            if list(base.columns) != list(copy_.columns) or not base.dtypes.equals(copy_.dtypes):
                return True
        if isinstance(base, (pd.DataFrame, pd.Series)):
            if base.attrs != attrs or base.flags.allows_duplicate_labels != flags:
                return True
            if not base.index.equals(copy_.index):
                return True
        return not base.equals(copy_)
    except Exception:
        return True


def probe_call(factory, fn, label):
    obj, base = factory()
    snap = snapshot(base)
    out = {"call": label}
    buf = io.StringIO()
    with warnings.catch_warnings(record=True) as w, contextlib.redirect_stdout(buf):
        warnings.simplefilter("always")
        try:
            res = fn(obj)
            out["returns"] = rkind(res)
        except Exception as e:  # noqa: BLE001
            out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    out["mutates"] = changed(base, snap)
    if buf.getvalue():
        out["prints"] = True
    warns = sorted({wi.category.__name__ for wi in w if issubclass(wi.category, (DeprecationWarning, FutureWarning))})
    if warns:
        out["warns"] = warns
    return out


def curated_calls(tname):
    df2 = pd.DataFrame({"a": [9]})
    C = {
        "DataFrame": {
            "update": lambda o: o.update(df2),
            "insert": lambda o: o.insert(0, "new", 1),
            "pop": lambda o: o.pop("a"),
            "pipe": lambda o: o.pipe(lambda d: d.shape),
            "apply": lambda o: o[["a", "b"]].apply(len),
            "eval": lambda o: o.eval("z = a + b", inplace=True),
            "query": lambda o: o.query("a > 1"),
            "get": lambda o: o.get("a"),
            "xs": lambda o: o.xs(0),
            "lookup_iter": None,
            "__setitem__": lambda o: o.__setitem__("z", 1),
            "set_axis": lambda o: o.set_axis(list("abcd")),
            "assign": lambda o: o.assign(z=1),
            "to_excel": None,
        },
        "Series": {
            "update": lambda o: o.update(pd.Series([9.0])),
            "pop": lambda o: o.pop(0),
            "pipe": lambda o: o.pipe(lambda s: s.size),
            "map": lambda o: o.map(str),
            "get": lambda o: o.get(0),
            "item": lambda o: o.head(1).item(),
        },
        "DataFrameGroupBy": {
            "get_group": lambda o: o.get_group("u"),
            "agg": lambda o: o.agg("sum"),
            "apply": lambda o: o.apply(len),
            "pipe": lambda o: o.pipe(lambda g: g.ngroups),
            "__iter__": lambda o: iter(o),
            "__getitem__": lambda o: o["a"],
        },
        "SeriesGroupBy": {
            "get_group": lambda o: o.get_group("u"),
            "agg": lambda o: o.agg("sum"),
            "apply": lambda o: o.apply(len),
        },
        "Resampler": {"agg": lambda o: o.agg("sum"), "apply": lambda o: o.apply(len), "get_group": None},
        "Index": {"map": lambda o: o.map(str), "get_loc": lambda o: o.get_loc("y"), "insert": lambda o: o.insert(0, "q")},
        "str": {"cat": lambda o: o.cat(), "split": lambda o: o.split("x"), "get_dummies": lambda o: o.get_dummies()},
        "cat": {"rename_categories": lambda o: o.rename_categories(["p", "q"])},
    }
    return {k: v for k, v in C.get(tname, {}).items() if v is not None}


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------


def census_class(tname, cls, factory, do_calls=True):
    members = {}
    dropped_private = 0
    deprecated = []
    for name in sorted(set(dir(cls))):
        if name.startswith("_"):
            dropped_private += 1
            continue
        try:
            raw = inspect.getattr_static(cls, name)
        except AttributeError:
            continue
        doc = member_doc(raw)
        # member-level deprecation = marker before the first numpydoc section header
        # (parameter-level markers, e.g. the pandas-3 `copy` keyword, live inside Parameters)
        head = _SECTION.split(doc, maxsplit=1)[0]
        # pandas 3 sometimes puts the `copy`-keyword note in the summary (Series.set_axis): "This keyword is ignored"
        if ".. deprecated::" in head and not re.search(r"\.\. deprecated::[^\n]*\n\s*This keyword", head):
            deprecated.append(name)
            continue
        kind = classify(raw)
        entry = {"kind": kind, "defined_in": None}
        for klass in cls.__mro__:
            if name in vars(klass):
                entry["defined_in"] = f"{klass.__module__}.{klass.__qualname__}"
                break
        if kind in ("method", "classmethod-staticmethod"):
            func = raw.__func__ if isinstance(raw, (classmethod, staticmethod)) else raw
            try:
                sig = inspect.signature(func, annotation_format=annotationlib.Format.STRING)
            except (TypeError, ValueError) as e:
                entry["signature_error"] = str(e)[:100]
                members[name] = entry
                continue
            plist = list(sig.parameters.values())
            if not isinstance(raw, staticmethod) and plist and plist[0].name in ("self", "cls"):
                plist = plist[1:]
            gl = dict(getattr(inspect.unwrap(func), "__globals__", {}))
            npd = npdoc_params(func)
            params = []
            for p in plist:
                rec = {
                    "name": p.name,
                    "pkind": p.kind.name,
                    "required": p.default is inspect.Parameter.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD),
                    "default": None if p.default is inspect.Parameter.empty else repr(p.default)[:80],
                    "annotation": None if p.annotation is inspect.Parameter.empty else str(p.annotation),
                    "np_type": npd.get(p.name),
                    "deprecated": p.name in npd.get("__deprecated__", ()),
                }
                if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                    rec.update(widget=UNKNOWN, source="varargs", resolved=None, choices=None, nullable=False, candidates=[])
                else:
                    rec.update(widget_for(tname, p.name, p.annotation, gl, p.default, npd.get(p.name)))
                params.append(rec)
            entry["params"] = params
            entry["returns_annotation"] = None if sig.return_annotation is inspect.Signature.empty else str(sig.return_annotation)
            entry["has_inplace"] = any(p["name"] == "inplace" for p in params)
        members[name] = entry

    # --- runtime probes ------------------------------------------------------
    if do_calls:
        cur = curated_calls(tname)
        for name, entry in members.items():
            if name in NEVER_CALL:
                entry["probe"] = {"skipped": "never-call"}
                continue
            if entry["kind"] in ("property", "accessor", "attribute"):
                entry["probe"] = probe_call(factory, lambda o, n=name: getattr(o, n), f".{name}")
            elif entry["kind"] in ("method", "classmethod-staticmethod") and "params" in entry:
                if name in cur:
                    entry["probe"] = probe_call(factory, cur[name], f"{name}(curated)")
                elif not any(p["required"] for p in entry["params"]) and entry["kind"] == "method":
                    entry["probe"] = probe_call(factory, lambda o, n=name: getattr(o, n)(), f"{name}()")
                if entry.get("has_inplace"):
                    others_required = any(p["required"] for p in entry["params"] if p["name"] != "inplace")
                    if not others_required:
                        entry["probe_inplace"] = probe_call(
                            factory, lambda o, n=name: getattr(o, n)(inplace=True), f"{name}(inplace=True)"
                        )
    return members, dropped_private, deprecated


def summarize(tname, members):
    counts = collections.Counter(e["kind"] for e in members.values())
    allp = [p for e in members.values() for p in e.get("params", [])]
    params = [p for p in allp if not p.get("deprecated")]
    named = [p for p in params if p["source"] != "varargs"]
    conc = [p for p in params if p["widget"] in CONCRETE]
    conc_strict = [p for p in params if p["widget"] in CONCRETE_STRICT]
    type_only = [p for p in params if p["widget"] in CONCRETE and p["source"] and "name" not in p["source"]]
    by_widget = collections.Counter(p["widget"] for p in params)
    by_source = collections.Counter(p["source"] or "none" for p in params)
    unknown_names = collections.Counter(p["name"] for p in params if p["widget"] == UNKNOWN and p["source"] != "varargs")
    methods_with_unknown = sorted(
        n
        for n, e in members.items()
        if any(p["widget"] == UNKNOWN and p["source"] != "varargs" and not p.get("deprecated") for p in e.get("params", []))
    )

    def pct(a, b):
        return round(100.0 * len(a) / len(b), 1) if b else None

    probes = [e["probe"] for e in members.values() if e.get("probe")]
    pstats = collections.Counter()
    for pr in probes:
        if "skipped" in pr:
            pstats["skipped"] += 1
        elif "error" in pr:
            pstats["error"] += 1
        elif pr.get("returns") in PANDAS_KINDS:
            pstats["pandas"] += 1
        else:
            pstats["non-pandas"] += 1
        if pr.get("mutates"):
            pstats["mutated"] += 1
    pstats["not_probed"] = len(members) - len(probes)
    return {
        "probe_stats": dict(pstats),
        "n_methods": counts["method"],
        "n_class_static": counts["classmethod-staticmethod"],
        "n_properties": counts["property"] + counts["attribute"],
        "n_accessors": counts["accessor"],
        "n_params": len(params),
        "n_params_deprecated_hidden": len(allp) - len(params),
        "n_params_named": len(named),
        "n_varargs": len(params) - len(named),
        "pct_concrete": pct(conc, params),
        "pct_concrete_named": pct([p for p in conc if p["source"] != "varargs"], named),
        "pct_concrete_strict": pct(conc_strict, params),
        "pct_type_only": pct(type_only, params),
        "by_widget": dict(by_widget.most_common()),
        "by_source": dict(by_source.most_common()),
        "unknown_param_names": unknown_names.most_common(),
        "methods_with_unknown": methods_with_unknown,
    }


def non_pandas_and_mutating(tname, members):
    rows = []
    for name, e in members.items():
        pr = e.get("probe") or {}
        pi = e.get("probe_inplace") or {}
        ret = pr.get("returns")
        flags = []
        if ret and ret not in PANDAS_KINDS:
            flags.append(f"returns {ret}")
        if pr.get("mutates"):
            flags.append("MUTATES")
        if pr.get("prints"):
            flags.append("prints")
        if pi:
            flags.append(
                "inplace=True -> " + (pi.get("returns") or pi.get("error", "?")) + (" (mutated)" if pi.get("mutates") else "")
            )
        elif e.get("has_inplace"):
            flags.append("has inplace= (not probed: other args required)")
        if name.startswith("to_") or name.startswith("iter") or name in ("items", "keys", "info", "style", "plot"):
            if not flags and not ret:
                flags.append(f"writer/iter (not probed: {pr.get('error') or pr.get('skipped') or 'args required'})")
        if flags:
            rows.append({"member": f"{tname}.{name}", "kind": e["kind"], "flags": flags, "probe": pr or None})
    return rows


# ---------------------------------------------------------------------------
# Top-level functions
# ---------------------------------------------------------------------------

TOPLEVEL = [
    "to_datetime",
    "to_numeric",
    "to_timedelta",
    "cut",
    "qcut",
    "get_dummies",
    "concat",
    "crosstab",
    "merge",
    "melt",
    "pivot_table",
    "wide_to_long",
]


def toplevel_census():
    d = tiny()
    wide = pd.DataFrame({"id": [1, 2], "A2020": [1.0, 2.0], "A2021": [3.0, 4.0]})
    calls = {
        "to_datetime": lambda: pd.to_datetime(pd.Series(["2020-01-01", "2020-02-01"])),
        "to_numeric": lambda: pd.to_numeric(pd.Series(["1", "2"])),
        "to_timedelta": lambda: pd.to_timedelta(pd.Series(["1D", "2h"])),
        "cut": lambda: pd.cut(d["a"], 2),
        "qcut": lambda: pd.qcut(d["a"], 2),
        "get_dummies": lambda: pd.get_dummies(d[["c", "s"]]),
        "concat": lambda: pd.concat([d, d]),
        "crosstab": lambda: pd.crosstab(d["c"], d["flag"]),
        "merge": lambda: pd.merge(d, d, on="a"),
        "melt": lambda: pd.melt(d, id_vars=["a"]),
        "pivot_table": lambda: pd.pivot_table(d, index="c", values="a"),
        "wide_to_long": lambda: pd.wide_to_long(wide, ["A"], i="id", j="yr"),
    }
    df_first_calls = {  # try passing a DataFrame as the first arg
        "to_datetime": lambda: pd.to_datetime(pd.DataFrame({"year": [2020], "month": [1], "day": [2]})),
        "to_numeric": lambda: pd.to_numeric(d[["a", "b"]]),
        "to_timedelta": lambda: pd.to_timedelta(d[["a"]]),
        "cut": lambda: pd.cut(d[["a"]], 2),
        "qcut": lambda: pd.qcut(d[["a"]], 2),
        "crosstab": lambda: pd.crosstab(d[["c"]], d["flag"]),
    }
    out = {}
    for fname in TOPLEVEL:
        f = getattr(pd, fname)
        sig = inspect.signature(f, annotation_format=annotationlib.Format.STRING)
        first = next(iter(sig.parameters.values()))
        gl = dict(getattr(inspect.unwrap(f), "__globals__", {}))
        tree = parse_ann(first.annotation, gl) if first.annotation is not inspect.Parameter.empty else None
        rec = {
            "first_param": first.name,
            "annotation": None if first.annotation is inspect.Parameter.empty else first.annotation,
            "resolved": tree_str(tree) if tree else None,
        }
        res = probe_call(lambda c=calls[fname]: (None, pd.DataFrame()), lambda _o, c=calls[fname]: c(), f"{fname}(Series/DataFrame)")
        rec["call_series_or_frame"] = res
        if fname in df_first_calls:
            rec["call_dataframe_first"] = probe_call(
                lambda: (None, pd.DataFrame()), lambda _o, c=df_first_calls[fname]: c(), f"{fname}(DataFrame)"
            )
        ann = rec["annotation"] or ""
        rec["annotated_frame_first"] = bool(re.search(r"DataFrame|Series|NDFrame", ann))
        rec["accepts_arraylike_first"] = bool(re.search(r"ArrayLike|ListLike|Iterable|Sequence|Mapping", ann))
        # "first arg is a DataFrame/Series" = the verified runtime call with a pandas object as first arg succeeded
        rec["first_arg_frame_or_series"] = "returns" in res
        rec["first_arg_is_list_of_frames"] = fname == "concat"
        out[fname] = rec
    return out


def all_toplevel_scan():
    """Bonus: every public top-level pandas function, classified by first-arg annotation."""
    rows = collections.Counter()
    detail = {}
    for name in sorted(n for n in dir(pd) if not n.startswith("_")):
        f = getattr(pd, name)
        if not isinstance(f, types.FunctionType):
            continue
        try:
            sig = inspect.signature(f, annotation_format=annotationlib.Format.STRING)
        except (TypeError, ValueError):
            continue
        ps = list(sig.parameters.values())
        if not ps:
            rows["no-params"] += 1
            detail[name] = "no-params"
            continue
        ann = ps[0].annotation if ps[0].annotation is not inspect.Parameter.empty else ""
        if re.search(r"DataFrame|Series|NDFrame", ann):
            cat = "frame/series annotated"
        elif re.search(r"ArrayLike|ListLike|Iterable|Sequence|Mapping|array", ann):
            cat = "array-like (Series accepted)"
        elif name.startswith("read_"):
            cat = "reader (path/buffer)"
        else:
            cat = "other"
        rows[cat] += 1
        detail[name] = f"{cat}: {ps[0].name}: {ann}"
    return dict(rows), detail


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main():
    t_all = time.perf_counter()
    targets = _targets()
    result = {
        "meta": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "numpydoc": NUMPYDOC_VERSION,
            "use_numpydoc": USE_NUMPYDOC,
            "machine": f"{platform.system()} {platform.machine()} {platform.processor() or ''}".strip(),
            "concrete_kinds": sorted(CONCRETE),
            "strict_kinds": sorted(CONCRETE_STRICT),
        },
        "classes": {},
    }
    timings = {}
    allrows = []
    for tname, factory, cls in targets:
        # static pass (timed separately, no calls)
        t0 = time.perf_counter()
        members, n_priv, deprecated = census_class(tname, cls, factory, do_calls=False)
        timings[tname] = round((time.perf_counter() - t0) * 1000, 1)
        # probing pass
        members, n_priv, deprecated = census_class(tname, cls, factory, do_calls=True)
        summ = summarize(tname, members)
        rows = non_pandas_and_mutating(tname, members)
        allrows.extend(rows)
        result["classes"][tname] = {
            "class": f"{cls.__module__}.{cls.__qualname__}",
            "summary": summ,
            "dropped_private": n_priv,
            "dropped_deprecated": deprecated,
            "non_pandas_or_mutating": rows,
            "members": members,
        }
    result["meta"]["static_census_ms_per_class"] = timings
    result["meta"]["static_census_ms_total"] = round(sum(timings.values()), 1)

    # overall
    allp = [p for c in result["classes"].values() for e in c["members"].values() for p in e.get("params", [])]
    params = [p for p in allp if not p.get("deprecated")]
    result["overall_deprecated_params"] = dict(collections.Counter(p["name"] for p in allp if p.get("deprecated")).most_common())
    named = [p for p in params if p["source"] != "varargs"]
    conc = [p for p in params if p["widget"] in CONCRETE]
    conc_named = [p for p in named if p["widget"] in CONCRETE]
    conc_strict = [p for p in params if p["widget"] in CONCRETE_STRICT]
    type_only = [p for p in params if p["widget"] in CONCRETE and p["source"] and "name" not in p["source"]]
    unknown = collections.Counter(p["name"] for p in named if p["widget"] == UNKNOWN)
    methods_unknown = sorted(
        f"{t}.{n}"
        for t, c in result["classes"].items()
        for n, e in c["members"].items()
        if any(p["widget"] == UNKNOWN and p["source"] != "varargs" and not p.get("deprecated") for p in e.get("params", []))
    )
    distinct_methods_unknown = sorted({m.split(".", 1)[1] for m in methods_unknown})
    # override curve: if the top-N unknown names were given a name->widget override
    curve = {}
    for n in (10, 20, 30, 50):
        top = {nm for nm, _ in unknown.most_common(n)}
        extra = sum(1 for p in named if p["widget"] == UNKNOWN and p["name"] in top)
        curve[f"top{n}"] = round(100.0 * (len(conc) + extra) / len(params), 1)
    result["overall"] = {
        "n_params": len(params),
        "n_params_named": len(named),
        "n_varargs": len(params) - len(named),
        "pct_concrete": round(100.0 * len(conc) / len(params), 1),
        "pct_concrete_named": round(100.0 * len(conc_named) / len(named), 1),
        "pct_concrete_strict": round(100.0 * len(conc_strict) / len(params), 1),
        "pct_type_only": round(100.0 * len(type_only) / len(params), 1),
        "by_widget": dict(collections.Counter(p["widget"] for p in params).most_common()),
        "by_source": dict(collections.Counter(p["source"] or "none" for p in params).most_common()),
        "unknown_param_names_top50": unknown.most_common(50),
        "n_distinct_unknown_names": len(unknown),
        "n_class_methods_with_unknown": len(methods_unknown),
        "n_distinct_method_names_with_unknown": len(distinct_methods_unknown),
        "class_methods_with_unknown": methods_unknown,
        "coverage_if_topN_unknown_names_overridden": curve,
        "varargs_names": dict(collections.Counter(p["name"] for p in params if p["source"] == "varargs").most_common()),
    }
    result["non_pandas_or_mutating"] = allrows
    result["toplevel"] = toplevel_census()
    scan_counts, scan_detail = all_toplevel_scan()
    result["toplevel_scan_all"] = {"counts": scan_counts, "detail": scan_detail}
    result["meta"]["wall_s_total"] = round(time.perf_counter() - t_all, 2)

    out = HERE / ("census.json" if USE_NUMPYDOC else "census_no_numpydoc.json")
    out.write_text(json.dumps(result, indent=1, default=repr))
    print_report(result)
    print(f"\nwrote {out}")


def print_report(r):
    m = r["meta"]
    print(f"# s6 census  python {m['python']}  pandas {m['pandas']}  numpydoc {m['numpydoc']} (used={m['use_numpydoc']})")
    print(f"static census: {m['static_census_ms_total']} ms total; wall incl. probes {m['wall_s_total']} s\n")
    print("| class | methods | cls/static | props | accessors | params | varargs | % concrete | % concrete (named only) | % strict (no scalar/values) | % type-only (no name rules) | static ms |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t, c in r["classes"].items():
        s = c["summary"]
        print(
            f"| {t} | {s['n_methods']} | {s['n_class_static']} | {s['n_properties']} | {s['n_accessors']} | {s['n_params']} | {s['n_varargs']} | "
            f"{s['pct_concrete']} | {s['pct_concrete_named']} | {s['pct_concrete_strict']} | {s['pct_type_only']} | {m['static_census_ms_per_class'][t]} |"
        )
    o = r["overall"]
    print(
        f"| **overall** | | | | | {o['n_params']} | {o['n_varargs']} | **{o['pct_concrete']}** | {o['pct_concrete_named']} | {o['pct_concrete_strict']} | {o['pct_type_only']} | |"
    )
    print("\nby widget:", o["by_widget"])
    print("by source:", o["by_source"])
    print("varargs:", o["varargs_names"])
    print("deprecated params hidden:", r["overall_deprecated_params"])
    print("\nunknown names top 50:", o["unknown_param_names_top50"])
    print("distinct unknown names:", o["n_distinct_unknown_names"], " class.methods with >=1 unknown:", o["n_class_methods_with_unknown"],
          " distinct method names:", o["n_distinct_method_names_with_unknown"])
    print("coverage if top-N unknown names overridden:", o["coverage_if_topN_unknown_names_overridden"])
    print("\n| class | members | probed->pandas | probed->non-pandas | probe error | not probed (args needed) | mutated base |")
    print("|---|---|---|---|---|---|---|")
    for t, c in r["classes"].items():
        ps = c["summary"]["probe_stats"]
        print(f"| {t} | {len(c['members'])} | {ps.get('pandas',0)} | {ps.get('non-pandas',0)} | {ps.get('error',0)} | {ps.get('not_probed',0)} | {ps.get('mutated',0)} |")
    for t, c in r["classes"].items():
        print(f"\n## {t}: dropped private={c['dropped_private']} deprecated={c['dropped_deprecated']}")
        print("unknown:", c["summary"]["unknown_param_names"][:15])
    print("\n## non-pandas / mutating")
    for row in r["non_pandas_or_mutating"]:
        print(f"- {row['member']} [{row['kind']}]: {'; '.join(row['flags'])}")
    print("\n## top-level")
    for f, rec in r["toplevel"].items():
        print(f"- {f}({rec['first_param']}: {rec['annotation']}) -> {rec['call_series_or_frame']}; df-first: {rec.get('call_dataframe_first')}")
    print("scan all top-level funcs:", r["toplevel_scan_all"]["counts"])


if __name__ == "__main__":
    main()
