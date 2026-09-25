"""Run generated figure code on a pyplot-free ``Figure`` and turn it into PNG bytes."""

from __future__ import annotations

import ast
import contextlib
import struct
import threading
import warnings
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import matplotlib
import matplotlib.style as mstyle
import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from ..errors import FramelabError
from ..ops.policy import MODULE_ATTRS, method_allowed
from .codegen import FigureCode

__all__ = ["PREVIEW_ROWS", "PlotCodeError", "Rendered", "build", "png_bytes", "validate_plot_code"]

PREVIEW_ROWS = 20_000
RENDER_LOCK = threading.RLock()  # rcParams and style contexts are process-global

FIGURE_ATTRS = frozenset({"subplots", "colorbar", "suptitle"})
AXES_ATTRS = frozenset(
    {
        "plot", "scatter", "bar", "barh", "grouped_bar", "hist", "boxplot", "violinplot", "pie",
        "stackplot", "step", "hexbin", "imshow", "set_title", "set_xlabel", "set_ylabel",
        "set_xscale", "set_yscale", "set_xlim", "set_ylim", "set_xticks", "set_yticks", "grid",
        "tick_params", "legend",
    }
)  # fmt: skip
# Data attributes figure code reads beyond the op policy (``values`` is a comprehension name).
DATA_ATTRS = frozenset({"index", "columns", "str", "dt", "ngroups"})
PLOT_DENIED = frozenset({"savefig", "canvas", "print_figure", "show", "draw", "set_canvas"})
PLOT_MODULE_ATTRS = {**MODULE_ATTRS, "np": MODULE_ATTRS["np"] | {"arange"}}

_ALLOWED_NODES = (
    ast.Module, ast.Assign, ast.Expr, ast.For, ast.Name, ast.Load, ast.Store, ast.Attribute,
    ast.Subscript, ast.Call, ast.keyword, ast.Constant, ast.List, ast.Tuple, ast.ListComp,
    ast.comprehension, ast.Compare, ast.BinOp, ast.UnaryOp, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
    ast.Gt, ast.GtE, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd, ast.Not,
)  # fmt: skip


class PlotCodeError(FramelabError, ValueError):
    code = "unsafe_code"


def validate_plot_code(code: str, readable: set[str], fig_var: str, axes_var: str) -> ast.Module:
    """Only the shapes the figure code generator emits; attributes are allowlisted per owner."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise PlotCodeError(f"generated figure code does not parse: {exc}") from None
    stored = {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
    }
    if stored & (readable - {fig_var, axes_var}):
        raise PlotCodeError(f"figure code may not rebind {sorted(stored & readable)}")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise PlotCodeError(f"{type(node).__name__} is not allowed in figure code")
        loads = isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        if loads and node.id not in readable and node.id not in stored:
            raise PlotCodeError(f"unknown name {node.id!r}")
        if not isinstance(node, ast.Attribute):
            continue
        attr = node.attr
        if attr.startswith("_") or attr in PLOT_DENIED:
            raise PlotCodeError(f"{attr!r} is not allowed in figure code")
        owner = node.value
        while isinstance(owner, ast.Subscript):
            owner = owner.value
        name = owner.id if isinstance(owner, ast.Name) else None
        if name in PLOT_MODULE_ATTRS:
            if attr not in PLOT_MODULE_ATTRS[name]:
                raise PlotCodeError(f"{name}.{attr} is not allowed")
        elif name == fig_var:
            if attr not in FIGURE_ATTRS:
                raise PlotCodeError(f"{fig_var}.{attr} is not allowed")
        elif name == axes_var:
            if attr not in AXES_ATTRS:
                raise PlotCodeError(f"{attr!r} is not an allowed axes method")
        elif not (method_allowed(attr) or attr in DATA_ATTRS):
            raise PlotCodeError(f"{attr!r} is not allowed in figure code")
    return tree


@dataclass
class Rendered:
    figure: Figure
    errors: dict[tuple[int, int], str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    sampled: bool = False


@contextlib.contextmanager
def style_context(style: str) -> Iterator[None]:
    with RENDER_LOCK, matplotlib.rc_context():
        if style == "default":
            yield
        else:
            with mstyle.context(style):
                yield


def _preview_rows(limit: int | None, flag: list[bool]) -> Callable[[Any, str], Any]:
    def preview_rows(data: Any, how: str) -> Any:
        if limit is None or len(data) <= limit:
            return data
        flag.append(True)
        if how == "sample":
            return data.sample(n=limit, random_state=0).sort_index()
        step = -(-len(data) // limit)
        return data.iloc[::step]

    return preview_rows


def _run(block_code: str, namespace: dict[str, Any], label: str) -> None:
    exec(compile(block_code, label, "exec"), namespace)  # noqa: S102 - validated above


def build(
    code: FigureCode,
    env: dict[str, Any],
    axes_var: str,
    *,
    preview_limit: int | None = None,
) -> Rendered:
    """Run ``code`` (executed variant) against ``env`` (variable name -> value).

    Must be called inside :func:`style_context`, which must also cover drawing and saving.
    Each layer runs on its own: a failing layer is reported and the rest still draw.
    """
    sampled: list[bool] = []
    namespace: dict[str, Any] = {
        "__builtins__": {},
        "pd": pd,
        "np": np,
        "Figure": Figure,
        "str": str,
        "_preview_rows": _preview_rows(preview_limit, sampled),
        **env,
    }
    readable = set(namespace) - {"__builtins__"}
    whole = "\n".join(line for b in code.blocks if b.error is None for line in b.executed)
    validate_plot_code(whole, readable, code.fig_var, axes_var)
    out = Rendered(figure=Figure())
    failed_preps: dict[tuple[int, int], str] = {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for block in code.blocks:
            key = (block.axes, block.layer) if block.kind == "layer" else None
            if block.error is not None:
                out.errors[key] = block.error  # type: ignore[index]
                continue
            if key is not None and key in failed_preps:
                out.errors[key] = failed_preps[key]
                continue
            try:
                _run("\n".join(block.executed), namespace, f"<framelab:{code.fig_var}>")
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                if block.kind == "header":
                    raise
                if block.kind == "prep":
                    for user in block.users:
                        failed_preps[user] = message
                elif key is not None:
                    out.errors[key] = message
                else:
                    out.warnings.append(message)
    out.figure = namespace[code.fig_var]
    out.warnings.extend(f"{w.category.__name__}: {w.message}" for w in caught)
    out.sampled = bool(sampled)
    return out


def png_bytes(figure: Figure, dpi: float) -> tuple[bytes, int, int]:
    """Draw and encode as PNG (filter 0 + zlib level 1: ~2.5x faster than Pillow, spike S5)."""
    figure.set_dpi(dpi)
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    rgba = np.asarray(canvas.buffer_rgba())
    height, width = rgba.shape[:2]
    raw = np.empty((height, width * 4 + 1), dtype=np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = rgba.reshape(height, width * 4)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw.tobytes(), 1))
        + chunk(b"IEND", b"")
    )
    return data, width, height
