"""Validate generated code against an AST allowlist and run it in one namespace."""

from __future__ import annotations

import ast
import datetime
import decimal
import linecache
import warnings
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ..errors import FramelabError
from ..ops.policy import (
    FUNC_REF,
    FUNC_TAKING,
    MODULE_ATTRS,
    OPAQUE,
    literal_func_spec_ok,
    method_allowed,
)

__all__ = ["MODULES", "UnsafeCode", "run_statement", "validate_code"]

MODULES: dict[str, Any] = {"pd": pd, "np": np, "datetime": datetime, "decimal": decimal}

_ALLOWED = (
    ast.Module,
    ast.Assign,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Attribute,
    ast.Subscript,
    ast.Call,
    ast.keyword,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Compare,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.And,
    ast.Or,
    ast.BitAnd,
    ast.BitOr,
    ast.Invert,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
)


class UnsafeCode(FramelabError, ValueError):
    code = "unsafe_code"


def _spec(node: ast.AST | None) -> Any:
    """A call argument as a plain spec for the string-function check (see ops.policy)."""
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_spec(e) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_spec(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return {i: _spec(v) for i, v in enumerate(node.values)}
    np_ref = isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    if np_ref and node.value.id == "np":  # type: ignore[union-attr]
        return FUNC_REF
    return OPAQUE


def _check_function_specs(node: ast.Call) -> None:
    """apply/agg/transform look strings up as methods: the executed call must only name kernels
    (a second line of defence behind op validation)."""
    if not (isinstance(node.func, ast.Attribute) and node.func.attr in FUNC_TAKING):
        return
    keywords = {k.arg: k.value for k in node.keywords if k.arg is not None}
    if any(k.arg is None for k in node.keywords):
        raise UnsafeCode("keyword unpacking is not allowed in function-taking calls")
    first = _spec(node.args[0]) if node.args else None
    func = _spec(keywords.pop("func", None))
    others = {k: _spec(v) for k, v in keywords.items()}
    if not literal_func_spec_ok(node.func.attr, first, func, others):
        raise UnsafeCode(f"{node.func.attr}() may only name pandas functions like 'sum'")


def validate_code(code: str, readable: set[str], result: str) -> ast.Module:
    """Allow only the tiny subset framelab generates; only ``result`` may be assigned."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise UnsafeCode(f"generated code does not parse: {exc}") from None
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            raise UnsafeCode("only single assignments are allowed")
        target = stmt.targets[0]
        if isinstance(target, ast.Subscript):
            target = target.value
        if not (isinstance(target, ast.Name) and target.id == result):
            raise UnsafeCode(f"generated code may only assign {result!r}")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise UnsafeCode(f"{type(node).__name__} is not allowed in generated code")
        if isinstance(node, ast.Call):
            _check_function_specs(node)
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise UnsafeCode(f"private attribute {node.attr!r} is not allowed")
        if isinstance(node, ast.Attribute):
            owner = node.value.id if isinstance(node.value, ast.Name) else None
            if owner in MODULE_ATTRS:
                if node.attr not in MODULE_ATTRS[owner]:
                    raise UnsafeCode(f"{owner}.{node.attr} is not allowed")
            elif not method_allowed(node.attr):
                raise UnsafeCode(f"{node.attr!r} is not allowed (it could write files or run code)")
        reads = isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        if reads and node.id not in readable and node.id != result:
            raise UnsafeCode(f"unknown name {node.id!r}")
    return tree


def run_statement(code: str, result: str, env: Mapping[str, Any]) -> tuple[Any, list[str]]:
    """Execute framelab-generated ``code`` and return (value bound to ``result``, warnings)."""
    tree = validate_code(code, set(MODULES) | set(env), result)
    filename = f"<framelab:{result}>"
    linecache.cache[filename] = (len(code), None, code.splitlines(keepends=True), filename)
    compiled = compile(tree, filename, "exec")
    namespace: dict[str, Any] = {"__builtins__": {}, **MODULES, **env}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        exec(compiled, namespace)  # noqa: S102 - validated framelab-generated code
    return namespace[result], [f"{w.category.__name__}: {w.message}" for w in caught]
