"""Python source literals for values that appear in generated code (labels, arguments)."""

from __future__ import annotations

import datetime as dt
import decimal
import math
from typing import Any

import numpy as np
import pandas as pd

from ..errors import FramelabError

__all__ = ["LiteralError", "emit_literal", "label_text"]


class LiteralError(FramelabError, TypeError):
    """The value cannot be written as a Python literal in generated code."""

    code = "unsupported_value"


def _str(s: str) -> str:
    r = repr(s)
    # Prefer double quotes; keep repr's choice when the text itself contains a double quote.
    if r[0] == "'" and '"' not in s:
        return '"' + r[1:-1] + '"'
    return r


def _seq(items: list[str], open_: str, close: str, single_tuple: bool = False) -> str:
    body = ", ".join(items)
    if single_tuple and len(items) == 1:
        body += ","
    return f"{open_}{body}{close}"


def emit_literal(value: Any) -> str:
    """Source code that evaluates to ``value`` with ``pd``/``np``/``datetime``/``decimal``."""
    if value is None:
        return "None"
    if value is pd.NaT:
        return "pd.NaT"
    if value is pd.NA:
        return "pd.NA"
    if isinstance(value, (bool, np.bool_)):
        return "True" if value else "False"
    if isinstance(value, np.datetime64):
        return emit_literal(pd.Timestamp(value))
    if isinstance(value, np.timedelta64):
        return emit_literal(pd.Timedelta(value))
    if isinstance(value, np.generic):
        return emit_literal(value.item())
    if isinstance(value, int):
        return repr(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "np.nan"
        if math.isinf(value):
            return "np.inf" if value > 0 else "-np.inf"
        return repr(value)
    if isinstance(value, complex):
        return repr(value)
    if isinstance(value, str):
        return _str(value)
    if isinstance(value, pd.Timestamp):
        if value.tz is None:
            return f"pd.Timestamp({_str(value.isoformat())})"
        return f"pd.Timestamp({_str(value.isoformat())}, tz={_str(str(value.tz))})"
    if isinstance(value, dt.datetime):
        return emit_literal(pd.Timestamp(value))
    if isinstance(value, dt.date):
        return f"datetime.date({value.year}, {value.month}, {value.day})"
    if isinstance(value, pd.Timedelta):
        return f"pd.Timedelta({_str(value.isoformat())})"
    if isinstance(value, dt.timedelta):
        return emit_literal(pd.Timedelta(value))
    if isinstance(value, decimal.Decimal):
        return f"decimal.Decimal({_str(str(value))})"
    if isinstance(value, pd.Period):
        return f"pd.Period({_str(str(value))}, freq={_str(value.freqstr)})"
    if isinstance(value, pd.Interval):
        left, right = emit_literal(value.left), emit_literal(value.right)
        return f"pd.Interval({left}, {right}, closed={_str(value.closed)})"
    if isinstance(value, tuple):
        return _seq([emit_literal(v) for v in value], "(", ")", single_tuple=True)
    if isinstance(value, list):
        return _seq([emit_literal(v) for v in value], "[", "]")
    if isinstance(value, dict):
        return _seq([f"{emit_literal(k)}: {emit_literal(v)}" for k, v in value.items()], "{", "}")
    raise LiteralError(f"cannot write a {type(value).__name__} as a literal")


def label_text(label: Any) -> str:
    """Human text for a row/column label (tuples joined with " / ", None -> "")."""
    if label is None:
        return ""
    if isinstance(label, tuple):
        return " / ".join(label_text(part) for part in label)
    return str(label)
