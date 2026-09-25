"""Render ops and expressions as Python source (display form and executed form)."""

from __future__ import annotations

import keyword
from collections.abc import Mapping
from dataclasses import dataclass

from ..ops import Op
from ..ops.values import (
    Arith,
    AttrE,
    BoolE,
    CallE,
    Cmp,
    Col,
    DictV,
    Func,
    GetCol,
    ListV,
    Lit,
    NegE,
    NodeRef,
    NotE,
    NpCall,
    OpError,
    This,
    Value,
)
from .literals import emit_literal
from .query import to_query
from .style import DEFAULT_STYLE, CodeStyle

__all__ = ["Rendered", "keyword_arg", "op_label", "render_expr", "render_op", "render_value"]

MAX_LABEL = 48
# ~x binds tighter than comparisons, arithmetic, & and |, so NotE never needs parentheses.
_ATOMS = (This, GetCol, CallE, AttrE, NodeRef, Lit, Col, Func, ListV, DictV, NotE, NpCall)
# Python precedence of arithmetic; unary minus sits between * and **.
_PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "//": 2, "%": 2, "**": 4}
_NEG = 3


@dataclass(frozen=True)
class Rendered:
    display: str
    executed: str


def _accessor(acc: tuple[str, ...]) -> str:
    return "".join(f".{a}" for a in acc)


def _arglist(args, kwargs, names: Mapping[str, str], this: str) -> str:
    parts = [render_value(a, names, this) for a in args]
    parts += [f"{k}={render_value(v, names, this)}" for k, v in kwargs]
    return ", ".join(parts)


def _operand(v: Value, names: Mapping[str, str], this: str) -> str:
    text = render_value(v, names, this)
    return text if isinstance(v, _ATOMS) else f"({text})"


def _base(v: Value, names: Mapping[str, str], this: str) -> str:
    """The object a method, attribute or subscript applies to: ``(a / b).round(2)``."""
    text = render_value(v, names, this)
    atom = isinstance(v, _ATOMS) and not isinstance(v, (NotE, Lit))
    return text if atom else f"({text})"


def _arith_prec(v: Value) -> int | None:
    if isinstance(v, Arith):
        return _PREC[v.op]
    if isinstance(v, NegE):
        return _NEG
    number = (
        isinstance(v, Lit) and isinstance(v.value, (int, float)) and not isinstance(v.value, bool)
    )
    if number and v.value < 0:  # type: ignore[union-attr]
        return _NEG  # "-3" reads like a unary minus
    return None


def _arith_operand(v: Value, parent: str, side: str, names: Mapping[str, str], this: str) -> str:
    """Parentheses only where Python needs them; ties on the right keep the evaluation order."""
    prec = _arith_prec(v)
    if prec is None:
        return _operand(v, names, this)
    text = render_value(v, names, this)
    if parent == "**":
        need = side == "left" or prec < _NEG
    elif side == "left":
        need = prec < _PREC[parent]
    else:
        need = prec <= _PREC[parent] or prec == _NEG
    return f"({text})" if need else text


def render_value(v: Value, names: Mapping[str, str], this: str) -> str:
    if isinstance(v, Lit):
        return emit_literal(v.value)
    if isinstance(v, Col):
        return emit_literal(v.label)
    if isinstance(v, NodeRef):
        return names[v.id]
    if isinstance(v, Func):
        return emit_literal(v.name) if v.ns == "str" else f"np.{v.name}"
    if isinstance(v, ListV):
        return "[" + ", ".join(render_value(i, names, this) for i in v.items) + "]"
    if isinstance(v, DictV):
        pairs = (
            f"{render_value(k, names, this)}: {render_value(x, names, this)}" for k, x in v.items
        )
        return "{" + ", ".join(pairs) + "}"
    return render_expr(v, names, this)


def render_expr(e: Value, names: Mapping[str, str], this: str) -> str:
    if isinstance(e, This):
        return this
    if isinstance(e, GetCol):
        return f"{_base(e.base, names, this)}[{emit_literal(e.label)}]"
    if isinstance(e, CallE):
        base = _base(e.base, names, this)
        return f"{base}{_accessor(e.accessor)}.{e.name}({_arglist(e.args, e.kwargs, names, this)})"
    if isinstance(e, AttrE):
        return f"{_base(e.base, names, this)}{_accessor(e.accessor)}.{e.name}"
    if isinstance(e, Arith):
        left = _arith_operand(e.left, e.op, "left", names, this)
        return f"{left} {e.op} {_arith_operand(e.right, e.op, 'right', names, this)}"
    if isinstance(e, Cmp):
        return f"{_operand(e.left, names, this)} {e.op} {_operand(e.right, names, this)}"
    if isinstance(e, NegE):
        inner = render_value(e.item, names, this)
        return (
            f"-{inner}"
            if _arith_prec(e.item) is None and isinstance(e.item, _ATOMS)
            else f"-({inner})"
        )
    if isinstance(e, NpCall):
        return f"np.{e.name}({', '.join(render_value(a, names, this) for a in e.args)})"
    if isinstance(e, BoolE):
        sep = " & " if e.op == "and" else " | "
        return sep.join(_operand(i, names, this) for i in e.items)
    if isinstance(e, NotE):
        return "~" + _operand(e.item, names, this)
    return render_value(e, names, this)


def _expression(op: Op, names: Mapping[str, str]) -> str:
    if op.kind == "func":
        return f"pd.{op.name}({_arglist(op.args, op.kwargs, names, '')})"
    base = names[op.target]  # type: ignore[index]
    if op.kind == "call":
        return (
            f"{base}{_accessor(op.accessor)}.{op.name}({_arglist(op.args, op.kwargs, names, base)})"
        )
    if op.kind == "attr":
        return f"{base}{_accessor(op.accessor)}.{op.name}"
    if op.kind == "getitem":
        return f"{base}[{emit_literal(op.key)}]"
    if op.kind == "filter":
        return f"{base}[{render_expr(op.expr, names, base)}]"  # type: ignore[arg-type]
    raise OpError(f"{op.kind} is not an expression op")


def keyword_arg(key: str, value: str) -> str:
    """``key=value`` when ``key`` is a valid keyword, else ``**{"key": value}``."""
    if key.isidentifier() and not keyword.iskeyword(key):
        return f"{key}={value}"
    return f"**{{{emit_literal(key)}: {value}}}"


def render_op(
    op: Op, result: str, names: Mapping[str, str], style: CodeStyle = DEFAULT_STYLE
) -> Rendered:
    """Statement(s) that bind ``result``; the executed form is a verified equivalent."""
    if op.kind == "setitem":
        base = names[op.target]  # type: ignore[index]
        value = render_expr(op.expr, names, result)  # type: ignore[arg-type]
        assign = f"{result}[{emit_literal(op.key)}] = {value}"
        # Copy-on-Write: copy(deep=False) is equal and O(1); the user sees the idiom.
        executed = f"{result} = {base}.copy(deep=False)\n{assign}"
        if style.column_assign == "assign" and isinstance(op.key, str):
            arg = keyword_arg(op.key, render_expr(op.expr, names, base))  # type: ignore[arg-type]
            return Rendered(f"{result} = {base}.assign({arg})", executed)
        return Rendered(f"{result} = {base}.copy()\n{assign}", executed)
    code = f"{result} = {_expression(op, names)}"
    if op.kind == "filter" and style.filter_style == "query":
        query = to_query(op.expr)
        if query is not None:
            base = names[op.target]  # type: ignore[index]
            return Rendered(f"{result} = {base}.query({emit_literal(query)})", code)
        return Rendered(f"# query() cannot express this condition: boolean mask\n{code}", code)
    return Rendered(code, code)


def _short(text: str) -> str:
    return text if len(text) <= MAX_LABEL else text[: MAX_LABEL - 1] + "…"


def op_label(op: Op, names: Mapping[str, str]) -> str:
    """A compact caption for the edge that creates a node, e.g. ``head(n=5)``."""
    if op.kind == "call":
        acc = "".join(f"{a}." for a in op.accessor)
        base = names.get(op.target or "", "")
        return _short(f"{acc}{op.name}({_arglist(op.args, op.kwargs, names, base)})")
    if op.kind == "attr":
        return _short("".join(f"{a}." for a in op.accessor) + op.name)
    if op.kind == "getitem":
        return _short(f"[{emit_literal(op.key)}]")
    if op.kind == "filter":
        return _short(render_expr(op.expr, names, names[op.target]))  # type: ignore[arg-type, index]
    if op.kind == "setitem":
        return _short(f"[{emit_literal(op.key)}] = …")
    return _short(f"pd.{op.name}(…)")
