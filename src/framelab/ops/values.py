"""Tagged values and inline expressions used as op arguments (JSON round-trippable)."""

from __future__ import annotations

import datetime as dt
import decimal
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ..errors import FramelabError

__all__ = [
    "ARITH_OPS",
    "ACCESSORS",
    "CMP_OPS",
    "Arith",
    "AttrE",
    "BoolE",
    "CallE",
    "Cmp",
    "Col",
    "DictV",
    "Expr",
    "Func",
    "GetCol",
    "ListV",
    "Lit",
    "NodeRef",
    "NegE",
    "NotE",
    "NpCall",
    "OpError",
    "This",
    "Value",
    "check_identifier",
    "check_method",
    "check_value",
    "decode_scalar",
    "encode_scalar",
    "node_refs",
    "value_from_json",
    "value_to_json",
]

CMP_OPS = frozenset({"==", "!=", "<", "<=", ">", ">="})
ARITH_OPS = frozenset({"+", "-", "*", "/", "//", "%", "**"})
ACCESSORS = frozenset({"str", "dt", "cat"})


class OpError(FramelabError, ValueError):
    """An op or value is malformed or not allowed."""

    code = "invalid_op"


def check_method(name: str) -> str:
    from .policy import method_allowed

    if not method_allowed(name):
        raise OpError(f"{name!r} is not allowed (it could write files or run code)")
    return name


def check_value(v: Any) -> Any:
    """Enforce the policy on every function reference and inline method call inside ``v``."""
    from .policy import ALLOWED_STR_FUNCS, np_func_allowed

    if isinstance(v, Func):
        allowed = np_func_allowed(v.name) if v.ns == "np" else v.name in ALLOWED_STR_FUNCS
        if v.ns not in ("str", "np") or not allowed:
            raise OpError(f"function {v.name!r} is not allowed")
    elif isinstance(v, CallE):
        check_method(v.name)
        check_value(v.base)
        for a in v.args:
            check_value(a)
        for _, x in v.kwargs:
            check_value(x)
    elif isinstance(v, (GetCol, AttrE)):
        check_value(v.base)
    elif isinstance(v, (Cmp, Arith)):
        check_value(v.left)
        check_value(v.right)
    elif isinstance(v, BoolE):
        for i in v.items:
            check_value(i)
    elif isinstance(v, (NotE, NegE)):
        check_value(v.item)
    elif isinstance(v, NpCall):
        if not np_func_allowed(v.name):
            raise OpError(f"function np.{v.name} is not allowed")
        for a in v.args:
            check_value(a)
    elif isinstance(v, ListV):
        for i in v.items:
            check_value(i)
    elif isinstance(v, DictV):
        for k, x in v.items:
            check_value(k)
            check_value(x)
    return v


def check_identifier(name: str, what: str) -> str:
    if not isinstance(name, str) or not name.isidentifier() or name.startswith("_"):
        raise OpError(f"{what} must be a public identifier, got {name!r}")
    return name


# ---- plain values ------------------------------------------------------------------------
@dataclass(frozen=True)
class Lit:
    value: Any

    def __hash__(self) -> int:
        return hash(("lit", repr(self.value)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Lit):
            return NotImplemented
        return _scalar_equal(self.value, other.value)


@dataclass(frozen=True)
class Col:
    """A column label of the op's target frame (kept distinct from literals for recipes)."""

    label: Any

    def __hash__(self) -> int:
        return hash(("col", repr(self.label)))


@dataclass(frozen=True)
class NodeRef:
    id: str


@dataclass(frozen=True)
class Func:
    """A function passed by name: a pandas kernel ("mean") or a numpy function (np.log)."""

    name: str
    ns: str = "str"


@dataclass(frozen=True)
class ListV:
    items: tuple[Value, ...]


@dataclass(frozen=True)
class DictV:
    items: tuple[tuple[Value, Value], ...]


# ---- inline expressions (evaluated relative to the op's target frame) ----------------------
@dataclass(frozen=True)
class This:
    """The op's target frame (the new copy for setitem)."""


@dataclass(frozen=True)
class GetCol:
    base: Expr
    label: Any

    def __hash__(self) -> int:
        return hash(("getcol", self.base, repr(self.label)))


@dataclass(frozen=True)
class CallE:
    base: Expr
    name: str
    accessor: tuple[str, ...] = ()
    args: tuple[Value, ...] = ()
    kwargs: tuple[tuple[str, Value], ...] = ()


@dataclass(frozen=True)
class AttrE:
    base: Expr
    name: str
    accessor: tuple[str, ...] = ()


@dataclass(frozen=True)
class Cmp:
    left: Expr
    op: str
    right: Value


@dataclass(frozen=True)
class Arith:
    left: Expr
    op: str
    right: Value


@dataclass(frozen=True)
class BoolE:
    op: str
    items: tuple[Expr, ...]


@dataclass(frozen=True)
class NotE:
    item: Expr


@dataclass(frozen=True)
class NegE:
    """Unary minus: ``-x``."""

    item: Value


@dataclass(frozen=True)
class NpCall:
    """A numpy function applied element-wise: ``np.sqrt(x)``, ``np.where(c, a, b)``."""

    name: str
    args: tuple[Value, ...] = ()


Expr = This | GetCol | CallE | AttrE | Cmp | Arith | BoolE | NotE | NegE | NpCall
Value = Lit | Col | NodeRef | Func | ListV | DictV | Expr
EXPR_TYPES = (This, GetCol, CallE, AttrE, Cmp, Arith, BoolE, NotE, NegE, NpCall)


# ---- scalar encoding (JSON-safe, lossless for literal-able values) --------------------------
def _scalar_equal(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    if isinstance(a, (tuple, list)) and isinstance(b, type(a)):
        return len(a) == len(b) and all(map(_scalar_equal, a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(_scalar_equal(a[k], b[k]) for k in a)
    try:
        return type(a) is type(b) and bool(a == b)
    except (TypeError, ValueError):
        return False


def encode_scalar(v: Any) -> Any:
    if isinstance(v, np.generic) and not isinstance(v, (np.datetime64, np.timedelta64)):
        v = v.item()
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if math.isnan(v):
            return {"$": "nan"}
        if math.isinf(v):
            return {"$": "inf", "sign": 1 if v > 0 else -1}
        return v
    if v is pd.NaT:
        return {"$": "nat"}
    if v is pd.NA:
        return {"$": "na"}
    if isinstance(v, (pd.Timestamp, np.datetime64, dt.datetime)):
        ts = pd.Timestamp(v)
        return {"$": "ts", "iso": ts.isoformat(), "tz": None if ts.tz is None else str(ts.tz)}
    if isinstance(v, (pd.Timedelta, np.timedelta64, dt.timedelta)):
        return {"$": "td", "iso": pd.Timedelta(v).isoformat()}
    if isinstance(v, dt.date):
        return {"$": "date", "iso": v.isoformat()}
    if isinstance(v, decimal.Decimal):
        return {"$": "dec", "v": str(v)}
    if isinstance(v, tuple):
        return {"$": "tuple", "items": [encode_scalar(x) for x in v]}
    if isinstance(v, list):
        return {"$": "list", "items": [encode_scalar(x) for x in v]}
    if isinstance(v, dict):
        return {"$": "dict", "items": [[encode_scalar(k), encode_scalar(x)] for k, x in v.items()]}
    raise OpError(f"cannot store a {type(v).__name__} in an op")


def decode_scalar(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if not isinstance(obj, dict) or "$" not in obj:
        raise OpError(f"invalid scalar {obj!r}")
    tag = obj["$"]
    if tag == "nan":
        return float("nan")
    if tag == "inf":
        return float("inf") if obj.get("sign", 1) > 0 else float("-inf")
    if tag == "nat":
        return pd.NaT
    if tag == "na":
        return pd.NA
    if tag == "ts":
        return (
            pd.Timestamp(obj["iso"], tz=obj.get("tz"))
            if obj.get("tz")
            else pd.Timestamp(obj["iso"])
        )
    if tag == "td":
        return pd.Timedelta(obj["iso"])
    if tag == "date":
        return dt.date.fromisoformat(obj["iso"])
    if tag == "dec":
        return decimal.Decimal(obj["v"])
    if tag == "tuple":
        return tuple(decode_scalar(x) for x in obj["items"])
    if tag == "list":
        return [decode_scalar(x) for x in obj["items"]]
    if tag == "dict":
        return {decode_scalar(k): decode_scalar(x) for k, x in obj["items"]}
    raise OpError(f"unknown scalar tag {tag!r}")


# ---- value (de)serialisation -----------------------------------------------------------------
def _accessor(acc: Any) -> tuple[str, ...]:
    acc = tuple(acc or ())
    for a in acc:
        if a not in ACCESSORS:
            raise OpError(f"unknown accessor {a!r}")
    return acc


def value_to_json(v: Value) -> dict[str, Any]:
    if isinstance(v, Lit):
        return {"t": "lit", "v": encode_scalar(v.value)}
    if isinstance(v, Col):
        return {"t": "col", "label": encode_scalar(v.label)}
    if isinstance(v, NodeRef):
        return {"t": "node", "id": v.id}
    if isinstance(v, Func):
        return {"t": "func", "name": v.name, "ns": v.ns}
    if isinstance(v, ListV):
        return {"t": "list", "items": [value_to_json(i) for i in v.items]}
    if isinstance(v, DictV):
        return {"t": "dict", "items": [[value_to_json(k), value_to_json(x)] for k, x in v.items]}
    if isinstance(v, This):
        return {"t": "this"}
    if isinstance(v, GetCol):
        return {"t": "getcol", "base": value_to_json(v.base), "label": encode_scalar(v.label)}
    if isinstance(v, CallE):
        return {
            "t": "call",
            "base": value_to_json(v.base),
            "name": v.name,
            "accessor": list(v.accessor),
            "args": [value_to_json(a) for a in v.args],
            "kwargs": [[k, value_to_json(x)] for k, x in v.kwargs],
        }
    if isinstance(v, AttrE):
        return {
            "t": "attr",
            "base": value_to_json(v.base),
            "name": v.name,
            "accessor": list(v.accessor),
        }
    if isinstance(v, (Cmp, Arith)):
        tag = "cmp" if isinstance(v, Cmp) else "arith"
        return {
            "t": tag,
            "op": v.op,
            "left": value_to_json(v.left),
            "right": value_to_json(v.right),
        }
    if isinstance(v, BoolE):
        return {"t": "bool", "op": v.op, "items": [value_to_json(i) for i in v.items]}
    if isinstance(v, NotE):
        return {"t": "not", "item": value_to_json(v.item)}
    if isinstance(v, NegE):
        return {"t": "neg", "item": value_to_json(v.item)}
    if isinstance(v, NpCall):
        return {"t": "np", "name": v.name, "args": [value_to_json(a) for a in v.args]}
    raise OpError(f"not a value: {v!r}")


def _expr(obj: Any) -> Expr:
    v = value_from_json(obj)
    if not isinstance(v, EXPR_TYPES):
        raise OpError(f"expected an expression, got {obj!r}")
    return v


def _operand(obj: Any) -> Value:
    """An arithmetic operand: an expression or a literal (``2 * x``)."""
    v = value_from_json(obj)
    if not isinstance(v, (Lit, *EXPR_TYPES)):
        raise OpError(f"expected an expression or a literal, got {obj!r}")
    return v


def value_from_json(obj: Any) -> Value:
    if not isinstance(obj, dict) or "t" not in obj:
        raise OpError(f"invalid value {obj!r}")
    t = obj["t"]
    if t == "lit":
        return Lit(decode_scalar(obj["v"]))
    if t == "col":
        return Col(decode_scalar(obj["label"]))
    if t == "node":
        if not isinstance(obj.get("id"), str):
            raise OpError("node reference without id")
        return NodeRef(obj["id"])
    if t == "func":
        ns = obj.get("ns", "str")
        if ns not in ("str", "np"):
            raise OpError(f"unknown function namespace {ns!r}")
        return check_value(Func(check_identifier(obj["name"], "function name"), ns))
    if t == "list":
        return ListV(tuple(value_from_json(i) for i in obj["items"]))
    if t == "dict":
        return DictV(tuple((value_from_json(k), value_from_json(x)) for k, x in obj["items"]))
    if t == "this":
        return This()
    if t == "getcol":
        return GetCol(_expr(obj["base"]), decode_scalar(obj["label"]))
    if t == "call":
        return CallE(
            _expr(obj["base"]),
            check_method(check_identifier(obj["name"], "method name")),
            _accessor(obj.get("accessor")),
            tuple(value_from_json(a) for a in obj.get("args", [])),
            tuple(
                (check_identifier(k, "keyword"), value_from_json(x))
                for k, x in obj.get("kwargs", [])
            ),
        )
    if t == "attr":
        return AttrE(
            _expr(obj["base"]),
            check_identifier(obj["name"], "attribute"),
            _accessor(obj.get("accessor")),
        )
    if t in ("cmp", "arith"):
        allowed = CMP_OPS if t == "cmp" else ARITH_OPS
        if obj.get("op") not in allowed:
            raise OpError(f"operator {obj.get('op')!r} is not allowed")
        if t == "cmp":
            return Cmp(_expr(obj["left"]), obj["op"], value_from_json(obj["right"]))
        return Arith(_operand(obj["left"]), obj["op"], _operand(obj["right"]))
    if t == "bool":
        if obj.get("op") not in ("and", "or"):
            raise OpError(f"boolean operator {obj.get('op')!r} is not allowed")
        items = tuple(_expr(i) for i in obj["items"])
        if len(items) < 2:
            raise OpError("a boolean combination needs at least two conditions")
        return BoolE(obj["op"], items)
    if t == "not":
        return NotE(_expr(obj["item"]))
    if t == "neg":
        return NegE(_operand(obj["item"]))
    if t == "np":
        name = check_identifier(obj.get("name"), "numpy function")
        args = obj.get("args", [])
        if not isinstance(args, list) or not 1 <= len(args) <= 3:
            raise OpError("a numpy function takes one to three arguments")
        return check_value(NpCall(name, tuple(_operand(a) for a in args)))
    raise OpError(f"unknown value tag {t!r}")


def node_refs(v: Any) -> list[str]:
    """Node ids referenced anywhere inside a value or expression, in order."""
    out: list[str] = []
    if isinstance(v, NodeRef):
        out.append(v.id)
    elif isinstance(v, ListV):
        for i in v.items:
            out += node_refs(i)
    elif isinstance(v, DictV):
        for k, x in v.items:
            out += node_refs(k) + node_refs(x)
    elif isinstance(v, (GetCol, AttrE)):
        out += node_refs(v.base)
    elif isinstance(v, CallE):
        out += node_refs(v.base)
        for a in v.args:
            out += node_refs(a)
        for _, x in v.kwargs:
            out += node_refs(x)
    elif isinstance(v, (Cmp, Arith)):
        out += node_refs(v.left) + node_refs(v.right)
    elif isinstance(v, BoolE):
        for i in v.items:
            out += node_refs(i)
    elif isinstance(v, (NotE, NegE)):
        out += node_refs(v.item)
    elif isinstance(v, NpCall):
        for a in v.args:
            out += node_refs(a)
    return out
