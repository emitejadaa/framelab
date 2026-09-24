"""Names of root DataFrames: detect the caller's variable names, sanitize and de-duplicate."""

from __future__ import annotations

import ast
import builtins
import keyword
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DEFAULT_ROOT_NAME",
    "RESERVED_NAMES",
    "RootSpec",
    "resolve_root_names",
    "sanitize_identifier",
    "scan_frame_for",
    "unique_name",
]

DEFAULT_ROOT_NAME = "df"
RESERVED_NAMES = frozenset({"pd", "np", "plt", "mpl", "fl"}) | frozenset(dir(builtins))
_IPYTHON_NOISE = re.compile(r"^(_+|_\d+|_i+\d*|In|Out|_oh|_dh|_ih|exit|quit|get_ipython)$")


@dataclass(frozen=True)
class RootSpec:
    """A root object plus the name it gets in generated code.

    ``source_expr`` is the user's own expression when it differs from ``name``
    (``dfs[0]`` for ``dfs_0``, ``df`` for ``explore(ventas=df)``); ``None`` otherwise.
    """

    name: str
    obj: Any = field(compare=False)
    source_expr: str | None = None


def sanitize_identifier(text: str, fallback: str = DEFAULT_ROOT_NAME) -> str:
    s = re.sub(r"\W+", "_", text.strip()).strip("_")
    if not s:
        return fallback
    if s[0].isdigit() or keyword.iskeyword(s) or s in RESERVED_NAMES:
        s = f"df_{s}"
    return s


def unique_name(base: str, taken: Iterable[str]) -> str:
    taken = set(taken)
    if base not in taken:
        return base
    i = 2
    while f"{base}_{i}" in taken:
        i += 1
    return f"{base}_{i}"


def scan_frame_for(obj: Any, frame: Any) -> list[str]:
    """Names bound to ``obj`` in the frame (locals first), skipping IPython's history names."""
    names: list[str] = []
    for scope in (frame.f_locals, frame.f_globals):
        for key, value in list(scope.items()):
            if value is obj and not _IPYTHON_NOISE.match(key) and key not in names:
                names.append(key)
    return names


def _call_node(frame: Any) -> ast.Call | None:
    try:
        import executing

        node = executing.Source.executing(frame).node
    except Exception:
        return None
    return node if isinstance(node, ast.Call) else None


def _is_simple_access(expr: ast.expr) -> bool:
    while isinstance(expr, (ast.Attribute, ast.Subscript)):
        if isinstance(expr, ast.Subscript) and not isinstance(expr.slice, (ast.Constant, ast.Name)):
            return False
        expr = expr.value
    return isinstance(expr, ast.Name)


def _name_for_expr(expr: ast.expr) -> tuple[str, str | None]:
    if isinstance(expr, ast.Name):
        return expr.id, None
    if _is_simple_access(expr):
        text = ast.unparse(expr)
        return sanitize_identifier(text), text
    return DEFAULT_ROOT_NAME, None


def resolve_root_names(
    args: Sequence[Any],
    kwargs: Mapping[str, Any],
    frame: Any,
    explicit_name: str | None = None,
) -> list[RootSpec]:
    """Name every root passed to ``explore()`` as the user wrote it in their code."""
    if explicit_name is not None and len(args) != 1:
        raise ValueError("name= can only be used with exactly one positional DataFrame")
    call = _call_node(frame) if frame is not None else None
    positional: list[ast.expr] | None = None
    keyword_exprs: dict[str, ast.expr] = {}
    if call is not None and not any(isinstance(a, ast.Starred) for a in call.args):
        if len(call.args) == len(args):
            positional = list(call.args)
        keyword_exprs = {k.arg: k.value for k in call.keywords if k.arg is not None}

    raw: list[tuple[str, Any, str | None]] = []
    for i, obj in enumerate(args):
        if explicit_name is not None:
            raw.append((sanitize_identifier(explicit_name), obj, None))
        elif positional is not None:
            name, src = _name_for_expr(positional[i])
            raw.append((name, obj, src))
        else:
            found = scan_frame_for(obj, frame) if frame is not None else []
            raw.append((found[0] if found else DEFAULT_ROOT_NAME, obj, None))
    for key, obj in kwargs.items():
        expr = keyword_exprs.get(key)
        src = None
        if expr is not None and not (isinstance(expr, ast.Name) and expr.id == key):
            src = ast.unparse(expr) if _is_simple_access(expr) else None
        raw.append((sanitize_identifier(key), obj, src))

    taken: set[str] = set()
    out: list[RootSpec] = []
    for name, obj, src in raw:
        final = unique_name(name, taken)
        taken.add(final)
        if final != name and src is None and name != DEFAULT_ROOT_NAME:
            src = name
        out.append(RootSpec(final, obj, src))
    return out
