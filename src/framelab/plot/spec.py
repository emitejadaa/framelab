"""The figure document: a JSON spec, validated and normalized before anything is drawn.

Specs come from the UI and from ``.framelab`` files, so every field is checked here: code is
generated only from normalized specs.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Collection
from typing import Any

import matplotlib.colors as mcolors

from ..errors import FramelabError
from ..naming import sanitize_identifier
from ..ops.values import OpError, decode_scalar
from .kinds import KINDS, LEGEND_LOCS, SCALES, catalog

__all__ = [
    "FILTER_OPS",
    "FigureSpecError",
    "SPEC_VERSION",
    "decode_ref",
    "new_layer",
    "new_spec",
    "normalize",
]

SPEC_VERSION = 1
FILTER_OPS = ("==", "!=", ">", ">=", "<", "<=", "contains", "isna", "notna")
ROW_MODES = ("all", "head", "tail", "sample", "filter")
MAX_GRID = 4
MAX_LAYERS = 24
MAX_TEXT = 300


class FigureSpecError(FramelabError, ValueError):
    code = "invalid_figure"


def _fail(where: str, message: str) -> FigureSpecError:
    return FigureSpecError(f"{where}: {message}")


def _text(value: Any, where: str, *, nullable: bool = False) -> str | None:
    if value is None:
        if nullable:
            return None
        return ""
    if not isinstance(value, str):
        raise _fail(where, "must be text")
    if len(value) > MAX_TEXT:
        raise _fail(where, f"is longer than {MAX_TEXT} characters")
    return value


def _number(value: Any, where: str, lo: float, hi: float, *, integer: bool = False) -> Any:
    ok = isinstance(value, int) if integer else isinstance(value, (int, float))
    if isinstance(value, bool) or not ok or not math.isfinite(value):
        raise _fail(where, "must be an integer" if integer else "must be a number")
    if not lo <= value <= hi:
        raise _fail(where, f"must be between {lo:g} and {hi:g}")
    return value


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise _fail(where, "must be true or false")
    return value


def _choice(value: Any, where: str, choices: Collection[Any]) -> Any:
    if value not in choices:
        raise _fail(where, f"must be one of {', '.join(map(str, choices))}")
    return value


# ---- data references ---------------------------------------------------------------------
def _ref(value: Any, where: str) -> dict[str, Any] | None:
    """``{"col": <encoded label>}``, ``{"index": true}`` or ``{"values": true}`` (Series)."""
    if value is None:
        return None
    if not isinstance(value, dict) or len(value) != 1:
        raise _fail(where, "must be a column, the index or the values")
    if value.get("index") is True:
        return {"index": True}
    if value.get("values") is True:
        return {"values": True}
    if "col" in value:
        try:
            decode_scalar(value["col"])
        except (OpError, KeyError, TypeError, ValueError) as exc:
            raise _fail(where, f"invalid column label ({exc})") from None
        return {"col": copy.deepcopy(value["col"])}
    raise _fail(where, "must be a column, the index or the values")


def decode_ref(ref: dict[str, Any]) -> tuple[str, Any]:
    """("col", label) | ("index", None) | ("values", None)."""
    if "col" in ref:
        return "col", decode_scalar(ref["col"])
    return ("index", None) if "index" in ref else ("values", None)


# ---- pieces ------------------------------------------------------------------------------
def _limits(value: Any, where: str) -> list[float | None]:
    if value is None:
        return [None, None]
    if not isinstance(value, list) or len(value) != 2:
        raise _fail(where, "must be [low, high]")
    out: list[float | None] = []
    for k, v in enumerate(value):
        out.append(None if v is None else _number(v, f"{where}[{k}]", -1e300, 1e300))
    if out[0] is not None and out[1] is not None and out[0] == out[1]:
        raise _fail(where, "low and high must differ")
    return out


def _rows(value: Any, where: str) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    if value is not None and not isinstance(value, dict):
        raise _fail(where, "must be an object")
    mode = _choice(raw.get("mode", "all"), f"{where}.mode", ROW_MODES)
    out: dict[str, Any] = {"mode": mode}
    if mode in ("head", "tail", "sample"):
        out["n"] = _number(raw.get("n", 100), f"{where}.n", 1, 10**9, integer=True)
    elif mode == "filter":
        out["column"] = _ref(raw.get("column"), f"{where}.column")
        if out["column"] is None or "index" in out["column"]:
            raise _fail(f"{where}.column", "choose a column to filter on")
        out["op"] = _choice(raw.get("op", "=="), f"{where}.op", FILTER_OPS)
        if out["op"] not in ("isna", "notna"):
            try:
                decode_scalar(raw.get("value"))
            except (OpError, KeyError, TypeError, ValueError) as exc:
                raise _fail(f"{where}.value", f"invalid value ({exc})") from None
            if out["op"] == "contains" and not isinstance(raw.get("value"), str):
                raise _fail(f"{where}.value", "contains needs text")
            out["value"] = copy.deepcopy(raw.get("value"))
    return out


def _prop(kind: str, key: str, value: Any, where: str) -> Any:
    prop = KINDS[kind].prop(key)
    if prop is None:
        raise _fail(where, f"{kind} has no property {key!r}")
    if prop.type == "color":
        if not isinstance(value, str) or not mcolors.is_color_like(value):
            raise _fail(where, "must be a color (a name like 'red' or '#3b82f6')")
        return value
    if prop.type in ("float", "int"):
        lo = -1e300 if prop.min is None else prop.min
        hi = 1e300 if prop.max is None else prop.max
        return _number(value, where, lo, hi, integer=prop.type == "int")
    if prop.type == "bool":
        return _bool(value, where)
    return _choice(value, where, prop.choices)


def _layer(value: Any, where: str, sources: Collection[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(where, "must be an object")
    kind_key = _choice(value.get("kind"), f"{where}.kind", KINDS)
    kind = KINDS[kind_key]
    source = value.get("source")
    if not isinstance(source, str) or source not in sources:
        raise _fail(f"{where}.source", f"unknown node {source!r}")
    ys = value.get("y") or []
    if not isinstance(ys, list):
        raise _fail(f"{where}.y", "must be a list")
    layer: dict[str, Any] = {
        "kind": kind_key,
        "source": source,
        "x": _ref(value.get("x"), f"{where}.x") if kind.x != "none" else None,
        "y": [_ref(y, f"{where}.y[{k}]") for k, y in enumerate(ys)],
        "hue": _ref(value.get("hue"), f"{where}.hue") if kind.hue else None,
        "color_by": _ref(value.get("color_by"), f"{where}.color_by") if kind.color_by else None,
        "size_by": _ref(value.get("size_by"), f"{where}.size_by") if kind.size_by else None,
        "rows": _rows(value.get("rows"), f"{where}.rows"),
        "props": {},
        "label": _text(value.get("label"), f"{where}.label"),
    }
    if None in layer["y"]:
        raise _fail(f"{where}.y", "cannot contain empty entries")
    if kind.y == "none":
        layer["y"] = []
    elif kind.y == "one":
        layer["y"] = layer["y"][:1]
    if layer["hue"] is not None:
        layer["y"] = layer["y"][:1]
        if layer["color_by"] is not None:
            raise _fail(where, "choose either 'split by' or 'color by', not both")
    props = value.get("props") or {}
    if not isinstance(props, dict):
        raise _fail(f"{where}.props", "must be an object")
    for key, v in props.items():
        if v is not None:
            layer["props"][key] = _prop(kind_key, key, v, f"{where}.props.{key}")
    return layer


def _axes(value: Any, where: str, sources: Collection[str]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    if value is not None and not isinstance(value, dict):
        raise _fail(where, "must be an object")
    layers = raw.get("layers") or []
    if not isinstance(layers, list):
        raise _fail(f"{where}.layers", "must be a list")
    if len(layers) > MAX_LAYERS:
        raise _fail(f"{where}.layers", f"at most {MAX_LAYERS} layers per axes")
    legend = raw.get("legend", "auto")
    return {
        "title": _text(raw.get("title"), f"{where}.title"),
        "xlabel": _text(raw.get("xlabel"), f"{where}.xlabel", nullable=True),
        "ylabel": _text(raw.get("ylabel"), f"{where}.ylabel", nullable=True),
        "xscale": _choice(raw.get("xscale", "linear"), f"{where}.xscale", SCALES),
        "yscale": _choice(raw.get("yscale", "linear"), f"{where}.yscale", SCALES),
        "xlim": _limits(raw.get("xlim"), f"{where}.xlim"),
        "ylim": _limits(raw.get("ylim"), f"{where}.ylim"),
        "grid": _bool(raw.get("grid", False), f"{where}.grid"),
        "legend": _choice(legend, f"{where}.legend", ("auto", "none", *LEGEND_LOCS)),
        "xrotation": _number(raw.get("xrotation", 0), f"{where}.xrotation", -90, 90),
        "layers": [_layer(ly, f"{where}.layers[{k}]", sources) for k, ly in enumerate(layers)],
    }


def normalize(raw: Any, sources: Collection[str]) -> dict[str, Any]:
    """A complete, validated copy of ``raw``; ``sources`` are the node ids layers may use."""
    if not isinstance(raw, dict):
        raise _fail("figure", "must be an object")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise _fail("name", "is required")
    styles = catalog()["styles"]
    nrows = _number(raw.get("nrows", 1), "nrows", 1, MAX_GRID, integer=True)
    ncols = _number(raw.get("ncols", 1), "ncols", 1, MAX_GRID, integer=True)
    axes_raw = raw.get("axes") or []
    if not isinstance(axes_raw, list):
        raise _fail("axes", "must be a list")
    axes_raw = (list(axes_raw) + [None] * (nrows * ncols))[: nrows * ncols]
    return {
        "version": SPEC_VERSION,
        "name": sanitize_identifier(name, fallback="fig"),
        "width": _number(raw.get("width", 8), "width", 1, 40),
        "height": _number(raw.get("height", 5), "height", 1, 40),
        "dpi": _number(raw.get("dpi", 100), "dpi", 30, 600, integer=True),
        "style": _choice(raw.get("style", "default"), "style", styles),
        "suptitle": _text(raw.get("suptitle"), "suptitle"),
        "nrows": nrows,
        "ncols": ncols,
        "sharex": _bool(raw.get("sharex", False), "sharex"),
        "sharey": _bool(raw.get("sharey", False), "sharey"),
        "axes": [_axes(a, f"axes[{k}]", sources) for k, a in enumerate(axes_raw)],
    }


def new_spec(name: str) -> dict[str, Any]:
    return normalize({"name": name}, ())


def new_layer(kind: str, source: str, **fields: Any) -> dict[str, Any]:
    return {"kind": kind, "source": source, **fields}
