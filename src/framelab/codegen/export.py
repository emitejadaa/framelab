"""A whole session as a Python script or a Jupyter notebook (nbformat 4.5)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .. import __version__
from .chain import chained_lines
from .literals import label_text
from .render import render_op
from .script import pipeline_lines, used_modules
from .style import CodeStyle, import_lines, restyle

__all__ = ["session_notebook", "session_script"]

_FAILED = frozenset({"error", "blocked", "cancelled"})


def _requirement(session: Any, node: Any) -> str:
    value = session.wait(node.id)
    shape = " × ".join(map(str, node.shape or ()))
    labels = list(value.columns) if isinstance(value, pd.DataFrame) else [value.name]
    shown = ", ".join(label_text(c) for c in labels[:5]) + (", …" if len(labels) > 5 else "")
    return f"{node.name} ({node.kind.value} {shape}: {shown})"


def _parts(session: Any, style: CodeStyle) -> tuple[list[str], list[str], list[str]]:
    """(data the code needs, statements, figure code) — unstyled."""
    nodes = session.nodes()
    failed = {n.id for n in nodes if not n.is_root and n.state.value in _FAILED}
    healthy = [n.id for n in nodes if n.id not in failed]
    needs = [_requirement(session, n) for n in nodes if n.is_root and not n.source_expr]
    if style.chained:
        consumed = {
            p for n in nodes if n.op is not None and n.id not in failed for p in n.op.parents()
        }
        leaves = [nid for nid in healthy if nid not in consumed]
        lines = chained_lines(session, leaves, style, root_mode="step")
    else:
        lines = pipeline_lines(session, healthy, "step", style)
    names = session.variable_names()
    for n in nodes:
        if n.id in failed:
            code = render_op(n.op, n.name, names, style).display
            why = f"{n.error.type}: {n.error.message}" if n.error else f"not run ({n.state.value})"
            commented = "\n".join(f"# {line}" for line in code.splitlines())
            lines.append(f"{commented}\n# ↑ {why.splitlines()[0] if why else ''}")
    figures = [session.plots.figure_display(fid) for fid in session.plots.ids()]
    return needs, lines, figures


def _roots(session: Any) -> str:
    return ", ".join(n.name for n in session.nodes() if n.is_root)


def _used(code: str, figures: list[str]) -> set[str]:
    return used_modules(code or "pass") | {"pd"} | ({"plt"} if figures else set())


def session_script(session: Any, style: CodeStyle | None = None) -> str:
    style = style or session.code_style()
    needs, lines, figures = _parts(session, style)
    body = "\n\n".join(part for part in ("\n".join(lines), *figures) if part)
    header = [f"# framelab session: {_roots(session)}", *(f"# Requires: {n}" for n in needs)]
    out = "\n".join(header)
    if style.include_imports:
        out += "\n\n" + "\n".join(import_lines(_used(body, figures), style))
    out += "\n\n" + restyle(body, style)
    if figures:
        out += f"\n\n{style.pyplot_alias}.show()"
    return out + "\n"


def _cell(kind: str, source: str, index: int) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "id": f"framelab-{index}",
        "cell_type": kind,
        "metadata": {},
        "source": source,
    }
    if kind == "code":
        cell.update(execution_count=None, outputs=[])
    return cell


def session_notebook(session: Any, style: CodeStyle | None = None) -> dict[str, Any]:
    style = style or session.code_style()
    needs, lines, figures = _parts(session, style)
    sources: list[tuple[str, str]] = [
        ("markdown", f"# framelab · {_roots(session)}\n\nExported by framelab {__version__}.")
    ]
    if needs:
        listed = "\n".join(f"- `{need}`" for need in needs)
        intro = "Define these variables before running the notebook:"
        sources.append(("markdown", f"{intro}\n\n{listed}"))
    if style.include_imports:
        used = _used("\n".join(lines + figures), figures)
        sources.append(("code", "\n".join(import_lines(used, style))))
    sources += [("code", restyle(code, style)) for code in lines + figures]
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
            "language_info": {"name": "python"},
        },
        "cells": [_cell(kind, text, i) for i, (kind, text) in enumerate(sources)],
    }
