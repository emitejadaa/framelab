"""Readable constructors for ops (tests, Python users, catalog defaults)."""

from __future__ import annotations

from typing import Any

from .op import Op
from .values import (
    EXPR_TYPES,
    Arith,
    BoolE,
    CallE,
    Cmp,
    Col,
    DictV,
    Func,
    GetCol,
    ListV,
    Lit,
    NodeRef,
    NotE,
    This,
    Value,
    node_refs,
)

VALUE_TYPES = (Lit, Col, NodeRef, Func, ListV, DictV, *EXPR_TYPES)


def to_value(v: Any) -> Value:
    if isinstance(v, VALUE_TYPES):
        return v  # type: ignore[return-value]
    if isinstance(v, list) and any(isinstance(i, VALUE_TYPES) for i in v):
        return ListV(tuple(to_value(i) for i in v))
    if isinstance(v, dict) and any(isinstance(x, VALUE_TYPES) for x in [*v, *v.values()]):
        return DictV(tuple((to_value(k), to_value(x)) for k, x in v.items()))
    return Lit(v)


def _kw(kwargs: dict[str, Any]) -> tuple[tuple[str, Value], ...]:
    return tuple((k, to_value(v)) for k, v in kwargs.items())


def call(target: str, name: str, *args: Any, accessor: tuple[str, ...] = (), **kwargs: Any) -> Op:
    return Op("call", target, name, tuple(accessor), tuple(map(to_value, args)), _kw(kwargs))


def attr(target: str, name: str, accessor: tuple[str, ...] = ()) -> Op:
    return Op("attr", target, name, tuple(accessor))


def getitem(target: str, key: Any) -> Op:
    return Op("getitem", target, key=key)


def where(target: str, cond: Any) -> Op:
    return Op("filter", target, expr=cond)


def setcol(target: str, label: Any, expr: Any) -> Op:
    return Op("setitem", target, key=label, expr=expr)


def func(name: str, *args: Any, **kwargs: Any) -> Op:
    return Op("func", None, name, (), tuple(map(to_value, args)), _kw(kwargs))


def this() -> This:
    return This()


def col(label: Any) -> GetCol:
    return GetCol(This(), label)


def ref_col(label: Any) -> Col:
    return Col(label)


def lit(v: Any) -> Lit:
    return Lit(v)


def node(node_id: str) -> NodeRef:
    return NodeRef(node_id)


def fn(name: str, ns: str = "str") -> Func:
    return Func(name, ns)


def method(
    expr: Any, name: str, *args: Any, accessor: tuple[str, ...] = (), **kwargs: Any
) -> CallE:
    return CallE(expr, name, tuple(accessor), tuple(map(to_value, args)), _kw(kwargs))


def _cmp(op: str):
    def build(left: Any, right: Any) -> Cmp:
        return Cmp(left, op, to_value(right))

    return build


eq, ne, gt, ge, lt, le = (_cmp(o) for o in ("==", "!=", ">", ">=", "<", "<="))


def _arith(op: str):
    def build(left: Any, right: Any) -> Arith:
        return Arith(left, op, to_value(right))

    return build


add, sub, mul, div = (_arith(o) for o in ("+", "-", "*", "/"))


def and_(*items: Any) -> BoolE:
    return BoolE("and", tuple(items))


def or_(*items: Any) -> BoolE:
    return BoolE("or", tuple(items))


def not_(item: Any) -> NotE:
    return NotE(item)


__all__ = [
    "add",
    "and_",
    "attr",
    "call",
    "col",
    "div",
    "eq",
    "fn",
    "func",
    "ge",
    "getitem",
    "gt",
    "le",
    "lit",
    "lt",
    "method",
    "mul",
    "ne",
    "node",
    "node_refs",
    "not_",
    "or_",
    "ref_col",
    "setcol",
    "sub",
    "this",
    "to_value",
    "where",
]
