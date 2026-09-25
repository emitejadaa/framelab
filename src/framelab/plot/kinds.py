"""Chart types and their editable properties: one source of truth for validation and the UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import matplotlib
import matplotlib.style as mstyle

__all__ = ["KINDS", "LEGEND_LOCS", "PER_POINT", "Kind", "Prop", "catalog"]

MARKERS = ("o", ".", "s", "^", "v", "D", "x", "+", "*")
LINESTYLES = ("-", "--", "-.", ":")
COLORMAPS = (
    "viridis", "plasma", "inferno", "magma", "cividis", "coolwarm", "RdYlGn", "Spectral",
    "Blues", "Greens", "Reds", "Oranges", "Purples", "Greys", "tab10", "tab20",
)  # fmt: skip
LEGEND_LOCS = (
    "best", "upper right", "upper left", "lower left", "lower right",
    "center left", "center right", "lower center", "upper center", "center",
)  # fmt: skip
SCALES = ("linear", "log", "symlog")


@dataclass(frozen=True)
class Prop:
    """One editable property. Defaults are matplotlib's own: unset props are never emitted.

    ``kwarg`` props go straight into the plotting call; the others (``colorbar``, ``autopct``,
    ``size_max``) are translated by the code generator.
    """

    key: str
    type: str  # color | float | int | bool | choice
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple[Any, ...] = ()
    kwarg: bool = True

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {"key": self.key, "type": self.type, "default": self.default}
        for attr in ("min", "max", "step"):
            if getattr(self, attr) is not None:
                out[attr] = getattr(self, attr)
        if self.choices:
            out["choices"] = list(self.choices)
        return out


@dataclass(frozen=True)
class Kind:
    """A chart type: which data it maps and which properties it takes.

    ``x``: "index" (index or a column, index by default), "column" (a column is required),
    "labels" (optional category labels) or "none".  ``y``: "one", "many" or "all" (many; empty
    means every column).
    """

    key: str
    family: str
    method: str
    x: str
    y: str
    hue: bool = False
    color_by: bool = False
    size_by: bool = False
    props: tuple[Prop, ...] = ()

    def prop(self, key: str) -> Prop | None:
        return next((p for p in self.props if p.key == key), None)

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "family": self.family,
            "method": self.method,
            "x": self.x,
            "y": self.y,
            "hue": self.hue,
            "color_by": self.color_by,
            "size_by": self.size_by,
            "props": [p.describe() for p in self.props],
        }


COLOR = Prop("color", "color")
EDGECOLOR = Prop("edgecolor", "color")
ALPHA = Prop("alpha", "float", 1.0, 0.0, 1.0, 0.05)
LINEWIDTH = Prop("linewidth", "float", 1.5, 0.0, 12.0, 0.25)
CMAP = Prop("cmap", "choice", "viridis", choices=COLORMAPS)
COLORBAR = Prop("colorbar", "bool", True, kwarg=False)
ORIENTATION = Prop("orientation", "choice", "vertical", choices=("vertical", "horizontal"))
SHOWMEANS = Prop("showmeans", "bool", False)

KINDS: dict[str, Kind] = {
    k.key: k
    for k in (
        Kind("line", "lines", "plot", "index", "many", hue=True, props=(
            COLOR, ALPHA, LINEWIDTH, Prop("linestyle", "choice", "-", choices=LINESTYLES),
            Prop("marker", "choice", "", choices=("", *MARKERS)),
            Prop("markersize", "float", 6.0, 0.0, 30.0, 1.0),
        )),
        Kind("scatter", "points", "scatter", "column", "one", hue=True, color_by=True,
             size_by=True, props=(
            COLOR, ALPHA, Prop("marker", "choice", "o", choices=MARKERS),
            Prop("s", "float", 36.0, 1.0, 1000.0, 1.0),
            Prop("size_max", "float", 200.0, 10.0, 2000.0, 10.0, kwarg=False),
            CMAP, COLORBAR, EDGECOLOR,
        )),
        Kind("bar", "bars", "bar", "index", "many", props=(
            COLOR, ALPHA, Prop("width", "float", 0.8, 0.05, 1.0, 0.05), EDGECOLOR,
        )),
        Kind("barh", "bars", "barh", "index", "many", props=(
            COLOR, ALPHA, Prop("height", "float", 0.8, 0.05, 1.0, 0.05), EDGECOLOR,
        )),
        Kind("hist", "distribution", "hist", "none", "many", hue=True, props=(
            Prop("bins", "int", 10, 1, 500, 1), COLOR, ALPHA,
            Prop("density", "bool", False), Prop("cumulative", "bool", False),
            Prop("histtype", "choice", "bar", choices=("bar", "step", "stepfilled")),
            Prop("stacked", "bool", False), EDGECOLOR,
        )),
        Kind("box", "distribution", "boxplot", "none", "many", hue=True, props=(
            ORIENTATION, SHOWMEANS, Prop("notch", "bool", False),
            Prop("showfliers", "bool", True),
        )),
        Kind("violin", "distribution", "violinplot", "none", "many", hue=True, props=(
            ORIENTATION, SHOWMEANS, Prop("showmedians", "bool", False),
        )),
        Kind("pie", "parts", "pie", "labels", "one", props=(
            Prop("autopct", "bool", False, kwarg=False),
            Prop("startangle", "float", 0.0, 0.0, 360.0, 5.0),
        )),
        Kind("area", "lines", "stackplot", "index", "many", props=(ALPHA,)),
        Kind("step", "lines", "step", "index", "one", hue=True, props=(
            COLOR, ALPHA, LINEWIDTH, Prop("where", "choice", "pre", choices=("pre", "mid", "post")),
        )),
        Kind("hexbin", "points", "hexbin", "column", "one", props=(
            Prop("gridsize", "int", 100, 2, 300, 1), CMAP, COLORBAR,
        )),
        Kind("heatmap", "matrix", "imshow", "none", "all", props=(CMAP, COLORBAR)),
    )
}  # fmt: skip

# One mark per row: their preview may use a subset of a big source.
PER_POINT = frozenset({"line", "scatter", "step", "area"})


def catalog() -> dict[str, Any]:
    """Everything the Plotter UI needs to build its forms."""
    return {
        "kinds": [k.describe() for k in KINDS.values()],
        "styles": ["default", *sorted(s for s in mstyle.available if not s.startswith("_"))],
        "colormaps": [c for c in COLORMAPS if c in matplotlib.colormaps],
        "legend_locs": list(LEGEND_LOCS),
        "scales": list(SCALES),
        "filter_ops": ["==", "!=", ">", ">=", "<", "<=", "contains", "isna", "notna"],
        "formats": ["png", "svg", "pdf", "jpg"],
    }
