"""An op: one pandas operation on one or more nodes, described as data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from .values import (
    ACCESSORS,
    EXPR_TYPES,
    Expr,
    OpError,
    Value,
    check_identifier,
    decode_scalar,
    encode_scalar,
    node_refs,
    value_from_json,
    value_to_json,
)

__all__ = ["OP_KINDS", "SCHEMA_VERSION", "Op", "OpKind", "op_from_json", "op_to_json"]

SCHEMA_VERSION = 1
OpKind = Literal["call", "attr", "getitem", "filter", "setitem", "func"]
OP_KINDS = frozenset({"call", "attr", "getitem", "filter", "setitem", "func"})


@dataclass(frozen=True)
class Op:
    kind: OpKind
    target: str | None = None
    name: str = ""
    accessor: tuple[str, ...] = ()
    args: tuple[Value, ...] = ()
    kwargs: tuple[tuple[str, Value], ...] = ()
    key: Any = None
    expr: Expr | None = None

    def __hash__(self) -> int:
        return hash(
            (
                self.kind,
                self.target,
                self.name,
                self.accessor,
                self.args,
                self.kwargs,
                repr(self.key),
                self.expr,
            )
        )

    def parents(self) -> tuple[str, ...]:
        refs: list[str] = [self.target] if self.target else []
        for a in self.args:
            refs += node_refs(a)
        for _, v in self.kwargs:
            refs += node_refs(v)
        if self.expr is not None:
            refs += node_refs(self.expr)
        return tuple(dict.fromkeys(refs))

    def validate(self) -> Op:
        if self.kind not in OP_KINDS:
            raise OpError(f"unknown op kind {self.kind!r}")
        for a in self.accessor:
            if a not in ACCESSORS:
                raise OpError(f"unknown accessor {a!r}")
        for k, _ in self.kwargs:
            check_identifier(k, "keyword")
        if self.kind == "func":
            if self.target is not None:
                raise OpError("a pandas function op has no target")
            check_identifier(self.name, "function name")
            if not callable(getattr(pd, self.name, None)) or self.name.startswith(
                ("read_", "to_pickle")
            ):
                raise OpError(f"pd.{self.name} is not an allowed pandas function")
            if not self.parents():
                raise OpError("a pandas function op must use at least one node")
            return self
        if not isinstance(self.target, str) or not self.target:
            raise OpError(f"a {self.kind} op needs a target node")
        if self.kind in ("call", "attr"):
            check_identifier(self.name, "method or attribute name")
        elif self.kind == "getitem":
            if self.key is None:
                raise OpError("getitem needs a key (a column label or a list of labels)")
        elif self.kind == "filter":
            if not isinstance(self.expr, EXPR_TYPES):
                raise OpError("filter needs a condition expression")
        elif self.kind == "setitem" and (self.key is None or not isinstance(self.expr, EXPR_TYPES)):
            raise OpError("setitem needs a column label and a value expression")
        return self


def op_to_json(op: Op) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_v": SCHEMA_VERSION,
        "kind": op.kind,
        "target": op.target,
        "name": op.name,
        "accessor": list(op.accessor),
        "args": [value_to_json(a) for a in op.args],
        "kwargs": [[k, value_to_json(v)] for k, v in op.kwargs],
    }
    if op.key is not None:
        data["key"] = encode_scalar(op.key)
    if op.expr is not None:
        data["expr"] = value_to_json(op.expr)
    return data


def op_from_json(data: Any) -> Op:
    if not isinstance(data, dict):
        raise OpError("an op must be a JSON object")
    if data.get("schema_v") != SCHEMA_VERSION:
        raise OpError(f"unsupported op schema version {data.get('schema_v')!r}")
    expr = value_from_json(data["expr"]) if "expr" in data else None
    op = Op(
        kind=data.get("kind"),
        target=data.get("target"),
        name=data.get("name", ""),
        accessor=tuple(data.get("accessor", ())),
        args=tuple(value_from_json(a) for a in data.get("args", [])),
        kwargs=tuple((k, value_from_json(v)) for k, v in data.get("kwargs", [])),
        key=decode_scalar(data["key"]) if "key" in data else None,
        expr=expr,  # type: ignore[arg-type]
    )
    return op.validate()
