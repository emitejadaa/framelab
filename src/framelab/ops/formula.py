"""Spreadsheet-like formulas for new columns: ``(precio - costo) * cantidad / 100``.

The text is parsed once, here, into the same structured expressions ops store (never code):
columns by name (backticks for names with spaces), numbers, text, parentheses, arithmetic,
comparisons, ``&``/``|``/``~`` and a small table of functions.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from typing import Any

from ..codegen.literals import label_text
from ..errors import FramelabError
from .values import (
    Arith,
    AttrE,
    BoolE,
    CallE,
    Cmp,
    GetCol,
    Lit,
    NegE,
    NotE,
    NpCall,
    OpError,
    This,
    Value,
    check_value,
)

__all__ = ["FUNCTIONS", "FormulaError", "parse_formula"]

MAX_FORMULA = 2000
_ARITH = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.Pow: "**",
}
_CMP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
# name -> (how, min args, max args); "np": np.name(args), "method": first_arg.name(rest)
FUNCTIONS: dict[str, tuple[str, int, int]] = {
    "abs": ("method", 1, 1),
    "round": ("method", 1, 2),
    "fillna": ("method", 2, 2),
    "clip": ("method", 3, 3),
    "sqrt": ("np", 1, 1),
    "exp": ("np", 1, 1),
    "log": ("np", 1, 1),
    "log10": ("np", 1, 1),
    "log2": ("np", 1, 1),
    "floor": ("np", 1, 1),
    "ceil": ("np", 1, 1),
    "sin": ("np", 1, 1),
    "cos": ("np", 1, 1),
    "maximum": ("np", 2, 2),
    "minimum": ("np", 2, 2),
    "where": ("np", 3, 3),
}
_BACKTICK = re.compile(r"`([^`]*)`")


class FormulaError(FramelabError, ValueError):
    code = "invalid_formula"

    def __init__(self, message: str, offset: int | None = None) -> None:
        super().__init__(message)
        self.offset = offset


class _Parser:
    def __init__(self, columns: Sequence[Any], quoted: dict[str, str]) -> None:
        self.by_text: dict[str, Any] = {}
        for label in columns:
            self.by_text.setdefault(label_text(label), label)
        self.quoted = quoted

    def fail(self, node: ast.AST, message: str) -> FormulaError:
        return FormulaError(message, getattr(node, "col_offset", None))

    def column(self, node: ast.AST, text: str) -> GetCol:
        if text not in self.by_text:
            raise self.fail(node, f"there is no column called {text!r}")
        return GetCol(This(), self.by_text[text])

    def value(self, node: ast.AST) -> Value:
        if isinstance(node, ast.Name):
            return self.column(node, self.quoted.get(node.id, node.id))
        if isinstance(node, ast.Constant):
            if node.value is None or isinstance(node.value, (bool, int, float, str)):
                return Lit(node.value)
            raise self.fail(node, "only numbers, text, True, False and None are allowed")
        if isinstance(node, ast.BinOp) and type(node.op) in _ARITH:
            return Arith(self.value(node.left), _ARITH[type(node.op)], self.value(node.right))
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitAnd, ast.BitOr)):
            op = "and" if isinstance(node.op, ast.BitAnd) else "or"
            return BoolE(op, (self.expr(node.left), self.expr(node.right)))
        if isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or"
            return BoolE(op, tuple(self.expr(v) for v in node.values))
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.UAdd):
                return self.value(node.operand)
            if isinstance(node.op, ast.USub):
                inner = self.value(node.operand)
                number = isinstance(inner, Lit) and isinstance(inner.value, (int, float))
                if number and not isinstance(inner.value, bool):  # type: ignore[union-attr]
                    return Lit(-inner.value)  # type: ignore[union-attr]
                return NegE(inner)
            return NotE(self.expr(node.operand))
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or type(node.ops[0]) not in _CMP:
                raise self.fail(node, "compare two things at a time (use & to combine)")
            return Cmp(
                self.expr(node.left), _CMP[type(node.ops[0])], self.value(node.comparators[0])
            )
        if isinstance(node, ast.Call):
            return self.call(node)
        if isinstance(node, ast.Attribute):
            base, accessor = self.accessor(node.value)
            return AttrE(base, self.name(node, node.attr), accessor)
        raise self.fail(node, "this is not supported in a formula")

    def expr(self, node: ast.AST) -> Any:
        v = self.value(node)
        if isinstance(v, Lit):
            raise self.fail(node, "a condition needs a column")
        return v

    def name(self, node: ast.AST, name: str) -> str:
        if name.startswith("_"):
            raise self.fail(node, f"{name!r} is not allowed")
        return name

    def accessor(self, node: ast.AST) -> tuple[Any, tuple[str, ...]]:
        if isinstance(node, ast.Attribute) and node.attr in ("str", "dt", "cat"):
            return self.expr(node.value), (node.attr,)
        return self.expr(node), ()

    def call(self, node: ast.Call) -> Value:
        if node.keywords:
            raise self.fail(node, "write function arguments without names")
        if isinstance(node.func, ast.Attribute):  # monto.round(2), nombre.str.upper()
            base, accessor = self.accessor(node.func.value)
            args = tuple(self.value(a) for a in node.args)
            return CallE(base, self.name(node, node.func.attr), accessor, args)
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            known = ", ".join(sorted(FUNCTIONS))
            raise self.fail(node, f"unknown function; available: {known}")
        name = node.func.id
        how, lo, hi = FUNCTIONS[name]
        if not lo <= len(node.args) <= hi:
            count = str(lo) if lo == hi else f"{lo} or {hi}"
            raise self.fail(node, f"{name}() takes {count} argument(s)")
        args = [self.value(a) for a in node.args]
        if how == "np":
            return NpCall(name, tuple(args))
        first = args[0]
        if isinstance(first, Lit):
            raise self.fail(node, f"the first argument of {name}() must use a column")
        return CallE(first, name, (), tuple(args[1:]))


def parse_formula(text: str, columns: Sequence[Any]) -> Value:
    """The expression for ``text``; column names resolve against ``columns`` (labels)."""
    if not isinstance(text, str) or not text.strip():
        raise FormulaError("write a formula, for example: precio * cantidad")
    if len(text) > MAX_FORMULA:
        raise FormulaError(f"the formula is longer than {MAX_FORMULA} characters")
    quoted: dict[str, str] = {}

    def swap(match: re.Match[str]) -> str:
        key = f"q{len(quoted)}_"
        while key in text:
            key += "_"
        quoted[key] = match.group(1)
        return key.ljust(len(match.group(0)))  # keep offsets for error positions

    source = _BACKTICK.sub(swap, text.strip())
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(
            f"the formula is incomplete or has a typo ({exc.msg})", exc.offset
        ) from None
    parser = _Parser(columns, {k.strip(): v for k, v in quoted.items()})
    value = parser.value(tree.body)
    try:
        return check_value(value)
    except OpError as exc:
        raise FormulaError(str(exc)) from None
