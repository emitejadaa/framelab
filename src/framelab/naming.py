"""Names of root DataFrames: detect the caller's variable names, sanitize and de-duplicate."""

from __future__ import annotations

import ast
import builtins
import inspect
import keyword
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .codegen.literals import label_text

__all__ = [
    "DEFAULT_ROOT_NAME",
    "MAX_NAME",
    "OP_ALIASES",
    "auto_node_name",
    "op_alias",
    "RESERVED_NAMES",
    "RootSpec",
    "resolve_root_names",
    "sanitize_identifier",
    "scan_frame_for",
    "unique_name",
    "user_frame",
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


def user_frame(frame: Any) -> Any:
    """Skip pandas-internal frames, so ``df.pipe(fl.explore)`` names ``df``, not ``obj``."""
    while frame is not None and frame.f_globals.get("__name__", "").startswith("pandas."):
        frame = frame.f_back
    return frame


def _static_lookup(expr: ast.expr, frame: Any) -> Any:
    """Value of a name or dotted attribute chain without running any user code."""
    if isinstance(expr, ast.Name):
        for scope in (frame.f_locals, frame.f_globals, vars(builtins)):
            if expr.id in scope:
                return scope[expr.id]
        raise LookupError(expr.id)
    if isinstance(expr, ast.Attribute):
        return inspect.getattr_static(_static_lookup(expr.value, frame), expr.attr)
    raise LookupError("not a plain name")


def _refers_to(expr: ast.expr, frame: Any, target: Any) -> bool:
    """Whether ``expr`` statically names ``target`` (unwrapping decorators)."""
    try:
        value = _static_lookup(expr, frame)
    except Exception:
        return False  # e.g. functools.partial(explore): cannot prove it
    return callable(value) and inspect.unwrap(value) is inspect.unwrap(target)


def _executing_call(frame: Any) -> ast.Call | None:
    try:
        import executing

        node = executing.Source.executing(frame).node
    except Exception:
        return None
    return node if isinstance(node, ast.Call) else None


def _pipe_receiver(call: ast.Call, frame: Any, callee: Any) -> ast.expr | None:
    """``ventas.pipe(fl.explore)`` -> the ``ventas`` expression.

    pandas 3 hands pipe'd functions a shallow copy, so the identity scan cannot find it.
    """
    func = call.func
    is_pipe = isinstance(func, ast.Attribute) and func.attr == "pipe" and bool(call.args)
    if is_pipe and _refers_to(call.args[0], frame, callee):
        return func.value
    return None


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
    callee: Any = None,
) -> list[RootSpec]:
    """Name every root passed to ``explore()`` as the user wrote it in their code."""
    if explicit_name is not None and len(args) != 1:
        raise ValueError("name= can only be used with exactly one positional DataFrame")
    raw_call = _executing_call(frame) if frame is not None else None
    call: ast.Call | None = None
    pipe_receiver: ast.expr | None = None
    if raw_call is not None:
        # When C code (sorted, max, map, ...) or pipe() calls explore, executing reports
        # the *outer* call, whose arguments are not the roots.
        if callee is None or _refers_to(raw_call.func, frame, callee):
            call = raw_call
        elif len(args) == 1 and not kwargs:
            pipe_receiver = _pipe_receiver(raw_call, frame, callee)
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
        elif pipe_receiver is not None:
            name, src = _name_for_expr(pipe_receiver)
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


MAX_NAME = 30
OP_ALIASES = {
    "sort_values": "sorted",
    "sort_index": "sorted",
    "drop_duplicates": "dedup",
    "fillna": "filled",
    "rename": "renamed",
    "drop": "dropped",
    "astype": "typed",
    "describe": "desc",
    "value_counts": "counts",
    "reset_index": "reset",
    "set_index": "indexed",
    "merge": "merged",
}


def _slug(text: str) -> str:
    return re.sub(r"\W+", "_", text).strip("_") or "col"


def _first_label(value: Any) -> Any:
    items = getattr(value, "items", None)
    if isinstance(items, tuple) and items:
        return _first_label(items[0])
    return getattr(value, "label", getattr(value, "value", value))


def op_alias(op: Any, names: Mapping[str, str]) -> str:
    """The short word an op adds to a name (``""`` for setitem: it keeps its parent's name)."""
    if op.kind == "setitem":
        return ""
    if op.kind == "getitem":
        return "cols" if isinstance(op.key, list) else _slug(label_text(op.key))
    if op.kind == "filter":
        return "filt"
    if op.kind == "call" and op.name == "groupby" and op.kwargs:
        by = dict(op.kwargs).get("by")
        return "by_" + _slug(label_text(_first_label(by))) if by is not None else "grouped"
    if op.kind == "call" and op.name == "merge" and op.args and hasattr(op.args[0], "id"):
        return names[op.args[0].id]
    return OP_ALIASES.get(op.name, op.name)


def auto_node_name(
    op: Any, names: Mapping[str, str], taken: Iterable[str], trail: Sequence[str] = ()
) -> str:
    """``{parent}_{alias}``, short, unique and a valid identifier.

    Past MAX_NAME the name keeps the root and the last steps: ``trail`` is the parent's
    ``(root, alias, alias, …)``; without it the root is the parent name's first word.
    """
    taken = set(taken)
    if op.target is not None:
        parent = names[op.target]
    else:
        refs = op.parents()
        parent = names[refs[0]] if refs else DEFAULT_ROOT_NAME
    if op.kind == "setitem":
        return unique_name(parent, taken)
    alias = op_alias(op, names)
    base = f"{parent}_{alias}"
    if len(base) > MAX_NAME:
        root = trail[0] if trail else parent.split("_")[0]
        recent = [a for a in trail[1:] if a][-1:]
        for candidate in ("_".join([root, *recent, alias]), f"{root}_{alias}"):
            base = candidate
            if len(base) <= MAX_NAME:
                break
        base = base[:MAX_NAME].rstrip("_")
    return unique_name(sanitize_identifier(base), taken)
