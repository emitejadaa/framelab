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
)


class UnsafeCode(FramelabError, ValueError):
    code = "unsafe_code"


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
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise UnsafeCode(f"private attribute {node.attr!r} is not allowed")
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
