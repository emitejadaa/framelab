"""Assemble the code for a node: its own step, or everything from the roots."""

from __future__ import annotations

import ast
from typing import Any

from .render import render_op

__all__ = ["node_script", "pipeline_lines", "used_imports"]

_IMPORTS = {
    "pd": "import pandas as pd",
    "np": "import numpy as np",
    "datetime": "import datetime",
    "decimal": "import decimal",
}


def used_imports(body: str) -> list[str]:
    names = {n.id for n in ast.walk(ast.parse(body)) if isinstance(n, ast.Name)}
    return [line for alias, line in _IMPORTS.items() if alias in names]


def pipeline_lines(session: Any, ids: list[str], mode: str = "origin") -> list[str]:
    """The statements that create ``ids`` (roots become a comment or ``name = expr``)."""
    names = session.variable_names()
    lines: list[str] = []
    for nid in ids:
        node = session.node(nid)
        if node.is_root:
            if node.source_expr:
                lines.append(f"{node.name} = {node.source_expr}")
            elif mode != "step":
                shape = " × ".join(map(str, node.shape or ())) or "?"
                lines.append(
                    f"# {node.name}: the {node.kind.value} ({shape}) passed to fl.explore()"
                )
            continue
        lines.append(render_op(node.op, node.name, names).display)
    return lines


def node_script(session: Any, key: str, mode: str = "origin") -> str:
    target = session.node(key)
    ids = [target.id] if mode == "step" else session.lineage(target.id)
    body = "\n".join(pipeline_lines(session, ids, mode))
    if mode == "step":
        return body
    imports = used_imports(body) or ["import pandas as pd"]
    return "\n".join(imports) + "\n\n" + body + "\n"
