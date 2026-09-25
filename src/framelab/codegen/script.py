"""Assemble the code for a node: its own step, or everything from the roots."""

from __future__ import annotations

import ast
from typing import Any

from .render import render_op
from .style import DEFAULT_STYLE, CodeStyle, import_lines, restyle

__all__ = ["node_script", "pipeline_lines", "root_line", "used_modules"]

_KNOWN = ("pd", "np", "plt", "datetime", "decimal")


def used_modules(body: str) -> set[str]:
    """Canonical module names (``pd``, ``np``…) the code reads."""
    names = {n.id for n in ast.walk(ast.parse(body)) if isinstance(n, ast.Name)}
    return {m for m in _KNOWN if m in names}


def root_line(node: Any, mode: str) -> str | None:
    if node.source_expr:
        return f"{node.name} = {node.source_expr}"
    if mode == "step":
        return None
    shape = " × ".join(map(str, node.shape or ())) or "?"
    return f"# {node.name}: the {node.kind.value} ({shape}) passed to fl.explore()"


def pipeline_lines(
    session: Any, ids: list[str], mode: str = "origin", style: CodeStyle = DEFAULT_STYLE
) -> list[str]:
    """The statements that create ``ids`` (roots become a comment or ``name = expr``)."""
    names = session.variable_names()
    lines: list[str] = []
    for nid in ids:
        node = session.node(nid)
        if node.is_root:
            line = root_line(node, mode)
            if line:
                lines.append(line)
            continue
        lines.append(render_op(node.op, node.name, names, style).display)
    return lines


def node_script(
    session: Any, key: str, mode: str = "origin", style: CodeStyle | None = None
) -> str:
    style = style or session.code_style()
    target = session.node(key)
    if style.chained and mode != "step":
        from .chain import chained_lines

        body = "\n".join(chained_lines(session, [target.id], style))
    else:
        ids = [target.id] if mode == "step" else session.lineage(target.id)
        body = "\n".join(pipeline_lines(session, ids, mode, style))
    shown = restyle(body, style)
    if mode == "step" or not style.include_imports:
        return shown
    imports = import_lines(used_modules(body) or {"pd"}, style)
    return "\n".join(imports) + "\n\n" + shown + "\n"
