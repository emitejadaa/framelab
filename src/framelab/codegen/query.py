"""Write a filter condition as a ``DataFrame.query`` string when query() can express it."""

from __future__ import annotations

import keyword
import math
from typing import Any

from ..ops.values import BoolE, CallE, Cmp, GetCol, ListV, Lit, NotE, This

__all__ = ["to_query"]


class _NoQuery(Exception):
    pass


def _column(e: Any) -> str:
    if not (isinstance(e, GetCol) and isinstance(e.base, This) and isinstance(e.label, str)):
        raise _NoQuery
    label = e.label
    if label.isidentifier() and not keyword.iskeyword(label) and label != "index":
        return label
    if not label or any(c in label for c in "`\n\\"):
        raise _NoQuery
    return f"`{label}`"


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return repr(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, str) and not any(c in value for c in "'\"\\\n`@"):
        return f"'{value}'"
    raise _NoQuery


def _operand(v: Any) -> str:
    if isinstance(v, GetCol):
        return _column(v)
    if isinstance(v, Lit):
        return _literal(v.value)
    raise _NoQuery


def _items(v: Any) -> list[Any]:
    if isinstance(v, ListV):
        return list(v.items)
    if isinstance(v, Lit) and isinstance(v.value, (list, tuple)):
        return [Lit(x) for x in v.value]
    raise _NoQuery


def _q(e: Any) -> str:
    if isinstance(e, Cmp):
        return f"{_column(e.left)} {e.op} {_operand(e.right)}"
    if isinstance(e, BoolE):
        parts = [f"({_q(i)})" if isinstance(i, BoolE) else _q(i) for i in e.items]
        return f" {e.op} ".join(parts)
    if isinstance(e, NotE):
        return f"not ({_q(e.item)})"
    simple_call = isinstance(e, CallE) and not e.accessor and not e.kwargs and len(e.args) == 1
    if simple_call and e.name == "isin":
        items = _items(e.args[0])
        if not items:
            raise _NoQuery
        return f"{_column(e.base)} in [{', '.join(_operand(i) for i in items)}]"
    raise _NoQuery


def to_query(expr: Any) -> str | None:
    """The query() text for ``expr``, or None when only a boolean mask can express it."""
    try:
        return _q(expr)
    except _NoQuery:
        return None
