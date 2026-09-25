"""Figure spec -> matplotlib code, as blocks the renderer can run one by one.

The displayed header uses pyplot (``fig, ax = plt.subplots(...)``); the executed header builds a
``Figure`` directly, never touching pyplot's global state. The body is identical in both, except
that the preview may run per-point layers on a subset of a big source (``_preview_rows``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..codegen.literals import emit_literal, label_text
from ..naming import unique_name
from ..ops.values import decode_scalar
from .kinds import KINDS, PER_POINT
from .spec import decode_ref

__all__ = ["Block", "FigureCode", "LayerError", "generate"]

INDENT = "    "


class LayerError(ValueError):
    """A layer that cannot be drawn with its current mapping (shown on the layer)."""


@dataclass
class Block:
    kind: str  # header | prep | layer | axes | figure
    display: list[str]
    executed: list[str]
    axes: int | None = None
    layer: int | None = None
    users: list[tuple[int, int]] = field(default_factory=list)  # prep: layers that read it
    error: str | None = None


@dataclass
class FigureCode:
    blocks: list[Block]
    fig_var: str
    style: str

    @property
    def uses(self) -> set[str]:
        """Module aliases the body reads (``pd``, ``np``)."""
        names: set[str] = set()
        for block in self.blocks:
            for line in block.display:
                names.update(re.findall(r"\b(pd|np)\.", line))
        return names

    def display(self, *, savefig: str | None = None) -> str:
        lines: list[str] = []
        for block in self.blocks:
            if block.error is not None:
                lines.append(f"# layer skipped: {block.error}")
            else:
                lines.extend(block.display)
        if savefig:
            lines.append(savefig)
        if self.style != "default":
            body = "\n".join(INDENT + ln if ln else ln for ln in lines)
            return f"with plt.style.context({emit_literal(self.style)}):\n{body}"
        return "\n".join(lines)


def _lit(value: Any) -> str:
    return emit_literal(value)


def _kw(name: str, value: Any) -> str:
    return f"{name}={_lit(value)}"


class _Gen:
    def __init__(self, spec: dict, names: dict[str, str], values: dict[str, Any], taken: set[str]):
        self.spec = spec
        self.names = names
        self.values = values
        self.taken = set(taken) | set(names.values())
        self.fig = spec["name"]
        self.taken.add(self.fig)
        suffix = self.fig[4:] if self.fig.startswith("fig_") else ""
        grid = spec["nrows"] * spec["ncols"] > 1
        self.axvar = self.fresh(("axs" if grid else "ax") + (f"_{suffix}" if suffix else ""))
        self.preps: dict[str, str] = {}  # prep code -> variable
        self.previews = 0

    def fresh(self, base: str) -> str:
        name = unique_name(base, self.taken)
        self.taken.add(name)
        return name

    # ---- axes -----------------------------------------------------------------------------
    def axes_expr(self, k: int) -> str:
        nrows, ncols = self.spec["nrows"], self.spec["ncols"]
        if nrows * ncols == 1:
            return self.axvar
        if nrows == 1 or ncols == 1:
            return f"{self.axvar}[{k}]"
        return f"{self.axvar}[{k // ncols}, {k % ncols}]"

    def header(self) -> Block:
        s = self.spec
        grid = [f"{s['nrows']}, {s['ncols']}"] if s["nrows"] * s["ncols"] > 1 else []
        share = [f"{k}=True" for k in ("sharex", "sharey") if s[k]] if grid else []
        size = f"figsize=({s['width']:g}, {s['height']:g})"
        layout = 'layout="constrained"'
        display = [
            f"{self.fig}, {self.axvar} = plt.subplots({', '.join([*grid, size, layout, *share])})"
        ]
        executed = [
            f"{self.fig} = Figure({size}, {layout})",
            f"{self.axvar} = {self.fig}.subplots({', '.join([*grid, *share])})",
        ]
        return Block("header", display, executed)

    # ---- data -------------------------------------------------------------------------------
    def source(self, layer: dict) -> tuple[str, Any]:
        sid = layer["source"]
        if sid not in self.values:
            raise LayerError("its data is not available")
        value = self.values[sid]
        if not isinstance(value, (pd.DataFrame, pd.Series)):
            raise LayerError(f"{self.names[sid]} is not a table (DataFrame or Series)")
        return self.names[sid], value

    def check_ref(self, ref: dict | None, value: Any, what: str) -> None:
        if ref is None:
            return
        kind, label = decode_ref(ref)
        if kind == "col":
            if not isinstance(value, pd.DataFrame):
                raise LayerError(f"{what}: a Series has no columns, use its values or index")
            if label not in value.columns:
                raise LayerError(f"{what}: there is no column {label_text(label)!r}")
        elif kind == "values" and not isinstance(value, pd.Series):
            raise LayerError(f"{what}: choose a column")

    def obj(self, ref: dict, value: Any) -> Any:
        kind, label = decode_ref(ref)
        if kind == "col":
            return value[label]
        return value.index if kind == "index" else value

    def expr(self, d: str, ref: dict) -> str:
        kind, label = decode_ref(ref)
        if kind == "col":
            return f"{d}[{_lit(label)}]"
        return f"{d}.index" if kind == "index" else d

    def text(self, ref: dict | None, value: Any) -> str:
        if ref is None:
            return ""
        kind, label = decode_ref(ref)
        if kind == "col":
            return label_text(label)
        name = value.index.name if kind == "index" else getattr(value, "name", None)
        return label_text(name) if name is not None else ""

    def axis(self, d: str, ref: dict, value: Any, *, categorical: bool) -> str:
        """Values for a position axis, converted when matplotlib cannot place them as they are."""
        e = self.expr(d, ref)
        o = self.obj(ref, value)
        is_index = isinstance(o, pd.Index)
        if isinstance(o, pd.MultiIndex):
            return f"{e}.to_flat_index().astype(str)"
        dtype = o.dtype
        if isinstance(dtype, pd.PeriodDtype):
            if categorical:
                return f"{e}.astype(str)"
            return f"{e}.to_timestamp()" if is_index else f"{e}.dt.to_timestamp()"
        if isinstance(dtype, pd.IntervalDtype):
            return f"{e}.astype(str)"
        if not categorical:
            return e
        if pd.api.types.is_bool_dtype(dtype):
            return f"{e}.astype(str)"
        if isinstance(dtype, pd.CategoricalDtype):
            cats = dtype.categories
            ok = pd.api.types.is_string_dtype(cats) or pd.api.types.is_numeric_dtype(cats)
            return e if ok else f"{e}.astype(str)"
        if dtype == np.dtype(object):
            inferred = pd.api.types.infer_dtype(o, skipna=False)
            return e if inferred in ("string", "empty") else f"{e}.astype(str)"
        return e

    def rows(
        self, layer: dict, name: str, value: Any, pos: tuple[int, int]
    ) -> tuple[str, Block | None]:
        rows = layer["rows"]
        mode = rows["mode"]
        if mode == "all":
            return name, None
        if mode in ("head", "tail"):
            code = f"{name}.{mode}(n={rows['n']})"
        elif mode == "sample":
            code = f"{name}.sample(n={min(rows['n'], len(value))}, random_state=0)"
        else:
            self.check_ref(rows["column"], value, "filter")
            col = self.expr(name, rows["column"])
            op = rows["op"]
            if op in ("isna", "notna"):
                mask = f"{col}.{op}()"
            elif op == "contains":
                mask = f"{col}.str.contains({_lit(rows['value'])}, regex=False, na=False)"
            else:
                mask = f"{col} {op} {_lit(decode_scalar(rows['value']))}"
            code = f"{name}[{mask}]"
        var = self.preps.get(code)
        if var is not None:
            return var, None
        var = self.preps[code] = self.fresh(f"{name}_plot")
        line = f"{var} = {code}"
        return var, Block("prep", [line], [line], users=[pos])

    # ---- layers -------------------------------------------------------------------------------
    def layer(self, k: int, j: int, layer: dict, legend: bool) -> list[Block]:
        name, value = self.source(layer)
        kind = KINDS[layer["kind"]]
        for what in ("x", "hue", "color_by", "size_by"):
            self.check_ref(layer[what], value, what)
        for y in layer["y"]:
            self.check_ref(y, value, "y")
        if layer["hue"] is not None and not isinstance(value, pd.DataFrame):
            raise LayerError("'split by' needs a DataFrame")
        ys = list(layer["y"])
        if not ys and isinstance(value, pd.Series) and kind.y != "none":
            ys = [{"values": True}]
        if not ys and kind.y in ("one", "many"):
            raise LayerError("choose the column(s) to plot")
        if kind.x == "column" and layer["x"] is None:
            raise LayerError("choose a column for x")
        blocks: list[Block] = []
        data, prep = self.rows(layer, name, value, (k, j))
        if prep is not None:
            blocks.append(prep)
        emit = getattr(self, f"_{layer['kind']}")
        before = set(self.taken)
        display = emit(self.axes_expr(k), data, value, layer, ys, legend)
        executed = display
        if layer["kind"] in PER_POINT:
            # same helper names as the displayed code; only the data variable differs
            after, self.taken = self.taken, before
            preview = f"_preview_{self.previews}"
            self.previews += 1
            how = "sample" if layer["kind"] == "scatter" else "stride"
            executed = [f"{preview} = _preview_rows({data}, {_lit(how)})"]
            executed += emit(self.axes_expr(k), preview, value, layer, ys, legend)
            self.taken = after | self.taken
        blocks.append(Block("layer", display, executed, axes=k, layer=j))
        return blocks

    def props(self, layer: dict, skip: tuple[str, ...] = ()) -> list[str]:
        kind = KINDS[layer["kind"]]
        return [
            _kw(p.key, layer["props"][p.key])
            for p in kind.props
            if p.kwarg and p.key in layer["props"] and p.key not in skip
        ]

    def label(self, layer: dict, default: str, legend: bool) -> list[str]:
        text = layer["label"] or default
        return [_kw("label", text)] if legend and text else []

    def loop(self, d: str, layer: dict) -> tuple[str, str, str]:
        key, group = self.fresh("key"), self.fresh("group")
        return (
            f"for {key}, {group} in {d}.groupby({_lit(decode_ref(layer['hue'])[1])}):",
            key,
            group,
        )

    def groups(self, d: str, layer: dict, y: dict) -> tuple[str, str]:
        var = self.fresh("groups")
        by = _lit(decode_ref(layer["hue"])[1])
        return f"{var} = {d}.groupby({by})[{_lit(decode_ref(y)[1])}]", var

    @staticmethod
    def call(target: str, args: list[str]) -> str:
        return f"{target}({', '.join(a for a in args if a)})"

    def _line(self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool) -> list[str]:
        return self._xy(ax, "plot", d, value, layer, ys, legend, self.props(layer))

    def _step(self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool) -> list[str]:
        return self._xy(ax, "step", d, value, layer, ys, legend, self.props(layer))

    def _xy(self, ax, method, d, value, layer, ys, legend, props) -> list[str]:
        x = layer["x"] or {"index": True}
        if layer["hue"] is not None:
            head, key, group = self.loop(d, layer)
            args = [self.axis(group, x, value, categorical=False), self.expr(group, ys[0])]
            label = [f"label={key}"] if legend else []
            return [head, INDENT + self.call(f"{ax}.{method}", args + label + props)]
        out = []
        for y in ys:
            args = [self.axis(d, x, value, categorical=False), self.expr(d, y)]
            label = self.label(layer, self.text(y, value), legend)
            out.append(self.call(f"{ax}.{method}", args + label + props))
        return out

    def _scatter(
        self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool
    ) -> list[str]:
        p = layer["props"]
        props = self.props(layer, skip=("cmap",))
        x, y = layer["x"], ys[0]
        if layer["hue"] is not None:
            head, key, group = self.loop(d, layer)
            args = [self.axis(group, x, value, categorical=False), self.expr(group, y)]
            size = self.size(group, layer)
            label = [f"label={key}"] if legend else []
            props = [a for a in props if not (size and a.startswith("s="))]
            return [head, INDENT + self.call(f"{ax}.scatter", args + size + label + props)]
        args = [self.axis(d, x, value, categorical=False), self.expr(d, y)]
        size = self.size(d, layer)
        props = [a for a in props if not (size and a.startswith("s="))]
        color: list[str] = []
        if layer["color_by"] is not None:
            color = [f"c={self.expr(d, layer['color_by'])}"]
            if "cmap" in p:
                color.append(_kw("cmap", p["cmap"]))
            props = [a for a in props if not a.startswith("color=")]
        call = self.call(
            f"{ax}.scatter", args + color + size + self.label(layer, "", legend) + props
        )
        if layer["color_by"] is not None and p.get("colorbar", True):
            var = self.fresh("points")
            bar_label = self.text(layer["color_by"], value)
            label = f", label={_lit(bar_label)}" if bar_label else ""
            return [f"{var} = {call}", f"{self.fig}.colorbar({var}, ax={ax}{label})"]
        return [call]

    def size(self, d: str, layer: dict) -> list[str]:
        if layer["size_by"] is None:
            return []
        col = self.expr(d, layer["size_by"])
        top = layer["props"].get("size_max", 200.0)
        return [f"s={col} / {col}.max() * {top:g}"]

    def _bar(self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool) -> list[str]:
        return self._bars(ax, "bar", d, value, layer, ys, legend)

    def _barh(self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool) -> list[str]:
        return self._bars(ax, "barh", d, value, layer, ys, legend)

    def _bars(self, ax, method, d, value, layer, ys, legend) -> list[str]:
        x = layer["x"] or {"index": True}
        cats = self.axis(d, x, value, categorical=True)
        if len(ys) == 1:
            args = [cats, self.expr(d, ys[0])]
            label = self.label(layer, self.text(ys[0], value), legend)
            return [self.call(f"{ax}.{method}", args + label + self.props(layer))]
        cols = [decode_ref(y)[1] for y in ys]
        orient = [_kw("orientation", "horizontal")] if method == "barh" else []
        labels = [_kw("labels", [label_text(c) for c in cols])] if legend else []
        props = self.props(layer, skip=("color", "width", "height"))
        heights = f"{d}[{_lit(cols)}].to_numpy()"
        return [
            self.call(
                f"{ax}.grouped_bar", [heights, f"tick_labels={cats}"] + labels + orient + props
            )
        ]

    def _hist(self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool) -> list[str]:
        if layer["hue"] is not None:
            line, groups = self.groups(d, layer, ys[0])
            data = f"[values.dropna() for key, values in {groups}]"
            labels = [f"label=[key for key, values in {groups}]"] if legend else []
            props = self.props(layer, skip=("color",))
            return [line, self.call(f"{ax}.hist", [data] + labels + props)]
        if len(ys) == 1:
            args = [f"{self.expr(d, ys[0])}.dropna()"]
            label = self.label(layer, self.text(ys[0], value), legend)
            return [self.call(f"{ax}.hist", args + label + self.props(layer))]
        data = "[" + ", ".join(f"{self.expr(d, y)}.dropna()" for y in ys) + "]"
        labels = [_kw("label", [self.text(y, value) for y in ys])] if legend else []
        return [self.call(f"{ax}.hist", [data] + labels + self.props(layer, skip=("color",)))]

    def _dist(self, ax, d, value, layer, ys) -> tuple[list[str], str, str]:
        """(prep lines, datasets expression, tick labels expression) for box and violin."""
        if layer["hue"] is not None:
            line, groups = self.groups(d, layer, ys[0])
            return (
                [line],
                f"[values.dropna() for key, values in {groups}]",
                f"[key for key, values in {groups}]",
            )
        data = "[" + ", ".join(f"{self.expr(d, y)}.dropna()" for y in ys) + "]"
        labels = [self.text(y, value) for y in ys]
        return [], data, _lit(labels) if any(labels) else ""

    def _box(self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool) -> list[str]:
        prep, data, labels = self._dist(ax, d, value, layer, ys)
        ticks = [f"tick_labels={labels}"] if labels else []
        return prep + [self.call(f"{ax}.boxplot", [data] + ticks + self.props(layer))]

    def _violin(
        self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool
    ) -> list[str]:
        prep, data, labels = self._dist(ax, d, value, layer, ys)
        out = prep + [self.call(f"{ax}.violinplot", [data] + self.props(layer))]
        if labels:
            axis = "y" if layer["props"].get("orientation") == "horizontal" else "x"
            groups = prep[0].split(" = ")[0] if prep else None
            stop = f"{groups}.ngroups + 1" if groups else str(len(ys) + 1)
            out.append(f"{ax}.set_{axis}ticks(np.arange(1, {stop}), labels={labels})")
        return out

    def _pie(self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool) -> list[str]:
        labels = self.axis(d, layer["x"] or {"index": True}, value, categorical=True)
        args = [self.expr(d, ys[0]), f"labels={labels}"]
        if layer["props"].get("autopct"):
            args.append(_kw("autopct", "%1.1f%%"))
        return [self.call(f"{ax}.pie", args + self.props(layer))]

    def _area(self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool) -> list[str]:
        x = self.axis(d, layer["x"] or {"index": True}, value, categorical=False)
        series = [self.expr(d, y) for y in ys]
        labels = [_kw("labels", [self.text(y, value) for y in ys])] if legend else []
        return [self.call(f"{ax}.stackplot", [x, *series] + labels + self.props(layer))]

    def _hexbin(
        self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool
    ) -> list[str]:
        args = [self.axis(d, layer["x"], value, categorical=False), self.expr(d, ys[0])]
        call = self.call(f"{ax}.hexbin", args + self.props(layer))
        if not layer["props"].get("colorbar", True):
            return [call]
        var = self.fresh("cells")
        return [f"{var} = {call}", f"{self.fig}.colorbar({var}, ax={ax})"]

    def _heatmap(
        self, ax: str, d: str, value: Any, layer: dict, ys: list, legend: bool
    ) -> list[str]:
        if not isinstance(value, pd.DataFrame):
            raise LayerError("a heatmap needs a DataFrame (for example a pivot table)")
        cols = [decode_ref(y)[1] for y in ys if "col" in y]
        shown = value[cols] if cols else value
        if not all(pd.api.types.is_numeric_dtype(t) for t in shown.dtypes):
            raise LayerError("every column of a heatmap must be numeric")
        out: list[str] = []
        matrix = d
        if cols:
            matrix = self.fresh("matrix")
            out.append(f"{matrix} = {d}[{_lit(cols)}]")
        var = self.fresh("cells")
        out.append(
            f"{var} = "
            + self.call(f"{ax}.imshow", [matrix, _kw("aspect", "auto")] + self.props(layer))
        )
        rows = layer["rows"]
        nrows = (
            min(rows["n"], len(shown)) if rows["mode"] in ("head", "tail", "sample") else len(shown)
        )
        if shown.shape[1] <= 60:
            out.append(f"{ax}.set_xticks(np.arange({matrix}.shape[1]), labels={matrix}.columns)")
        if nrows <= 60:
            out.append(f"{ax}.set_yticks(np.arange({matrix}.shape[0]), labels={matrix}.index)")
        if layer["props"].get("colorbar", True):
            out.append(f"{self.fig}.colorbar({var}, ax={ax})")
        return out

    # ---- axes decorations ---------------------------------------------------------------------
    def wants_legend(self, axes: dict) -> bool:
        if axes["legend"] == "none":
            return False
        if axes["legend"] != "auto":
            return True
        series = 0
        for layer in axes["layers"]:
            if layer["kind"] in ("pie", "box", "violin", "heatmap", "hexbin"):
                continue
            if layer["hue"] is not None or layer["label"]:
                return True
            series += max(len(layer["y"]), 1)
        return series > 1

    def auto_labels(self, axes: dict) -> tuple[str, str]:
        xs: set[str] = set()
        ys: set[str] = set()
        for layer in axes["layers"]:
            value = self.values.get(layer["source"])
            if not isinstance(value, (pd.DataFrame, pd.Series)):
                continue
            try:
                kind = layer["kind"]
                ytexts = [self.text(y, value) for y in layer["y"]] or (
                    [self.text({"values": True}, value)] if isinstance(value, pd.Series) else []
                )
                hue = self.text(layer["hue"], value) if layer["hue"] else ""
                xt = self.text(layer["x"] or {"index": True}, value)
                if kind in ("line", "step", "scatter", "hexbin", "area", "bar"):
                    xs.add(xt)
                    ys.update(ytexts if len(ytexts) == 1 else [""])
                elif kind == "barh":
                    ys.add(xt)
                    xs.update(ytexts if len(ytexts) == 1 else [""])
                elif kind == "hist":
                    xs.update(ytexts if len(ytexts) == 1 else [""])
                elif kind in ("box", "violin"):
                    horizontal = layer["props"].get("orientation") == "horizontal"
                    values_axis, cats_axis = (xs, ys) if horizontal else (ys, xs)
                    if hue:
                        cats_axis.add(hue)
                        values_axis.update(ytexts[:1])
            except Exception:
                continue
        pick = lambda s: next(iter(s)) if len(s) == 1 else ""  # noqa: E731
        return pick(xs), pick(ys)

    def decorations(self, k: int, axes: dict, legend: bool) -> Block:
        ax = self.axes_expr(k)
        out: list[str] = []
        if axes["title"]:
            out.append(f"{ax}.set_title({_lit(axes['title'])})")
        auto_x, auto_y = self.auto_labels(axes)
        xlabel = auto_x if axes["xlabel"] is None else axes["xlabel"]
        ylabel = auto_y if axes["ylabel"] is None else axes["ylabel"]
        if xlabel:
            out.append(f"{ax}.set_xlabel({_lit(xlabel)})")
        if ylabel:
            out.append(f"{ax}.set_ylabel({_lit(ylabel)})")
        for axis in ("x", "y"):
            if axes[f"{axis}scale"] != "linear":
                out.append(f"{ax}.set_{axis}scale({_lit(axes[f'{axis}scale'])})")
        if axes["grid"]:
            out.append(f"{ax}.grid(True)")
        if axes["xrotation"]:
            out.append(f'{ax}.tick_params(axis="x", labelrotation={axes["xrotation"]:g})')
        if legend:
            args = []
            if axes["legend"] not in ("auto", "none"):
                args.append(_kw("loc", axes["legend"]))
            hues = {
                self.text(ly["hue"], self.values.get(ly["source"]))
                for ly in axes["layers"]
                if ly["hue"] is not None and isinstance(self.values.get(ly["source"]), pd.DataFrame)
            }
            if len(hues) == 1 and next(iter(hues)):
                args.append(_kw("title", next(iter(hues))))
            out.append(f"{ax}.legend({', '.join(args)})")
        for axis in ("x", "y"):
            lo, hi = axes[f"{axis}lim"]
            if lo is not None and hi is not None:
                out.append(f"{ax}.set_{axis}lim({lo!r}, {hi!r})")
            elif lo is not None or hi is not None:
                side = ("left", "right") if axis == "x" else ("bottom", "top")
                which, v = (side[0], lo) if lo is not None else (side[1], hi)
                out.append(f"{ax}.set_{axis}lim({which}={v!r})")
        return Block("axes", out, out, axes=k)


def generate(
    spec: dict,
    names: dict[str, str],
    values: dict[str, Any],
    taken: set[str] | frozenset = frozenset(),
) -> FigureCode:
    """Code blocks for a normalized ``spec``; ``names``/``values`` map node ids to names/data."""
    gen = _Gen(spec, names, values, set(taken))
    blocks = [gen.header()]
    for k, axes in enumerate(spec["axes"]):
        legend = gen.wants_legend(axes)
        for j, layer in enumerate(axes["layers"]):
            try:
                blocks.extend(gen.layer(k, j, layer, legend))
            except LayerError as exc:
                blocks.append(Block("layer", [], [], axes=k, layer=j, error=str(exc)))
        deco = gen.decorations(k, axes, legend)
        if deco.display:
            blocks.append(deco)
    if spec["suptitle"]:
        line = f"{gen.fig}.suptitle({_lit(spec['suptitle'])})"
        blocks.append(Block("figure", [line], [line]))
    return FigureCode(blocks, gen.fig, spec["style"])
