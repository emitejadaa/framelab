"""Chained style: each variable is one expression that chains its single-use steps.

A node becomes part of its consumer's expression when exactly one node in the lineage consumes
it and that consumer can chain (or takes it as an argument). Roots, targets, branch points and
steps that cannot be written as a chain (non-string column keys) stay variables.
"""

from __future__ import annotations

import json
from typing import Any

from ..naming import unique_name
from ..ops import Op, op_to_json
from .literals import emit_literal
from .query import to_query
from .render import _accessor, _arglist, keyword_arg, render_expr, render_op
from .script import root_line
from .style import CodeStyle

__all__ = ["chained_lines"]

MAX_LINE = 88
Chain = tuple[str, list[tuple[str, str]]]  # head expression, steps ("dot" | "sub", text)


def _uses_this(op: Op) -> bool:
    data = op_to_json(op)
    return '"this"' in json.dumps([data.get("args"), data.get("kwargs")])


def _chainable(op: Op) -> bool:
    if op.kind not in ("call", "attr", "getitem", "filter", "setitem"):
        return False
    if op.kind == "setitem" and not isinstance(op.key, str):
        return False
    return not _uses_this(op)


def _step(op: Op, texts: dict[str, str], lam: str, style: CodeStyle) -> tuple[str, str]:
    if op.kind == "call":
        args = _arglist(op.args, op.kwargs, texts, lam)
        return "dot", f"{_accessor(op.accessor)}.{op.name}({args})"
    if op.kind == "attr":
        return "dot", f"{_accessor(op.accessor)}.{op.name}"
    if op.kind == "getitem":
        return "sub", f"[{emit_literal(op.key)}]"
    if op.kind == "filter":
        query = to_query(op.expr) if style.filter_style == "query" else None
        if query is not None:
            return "dot", f".query({emit_literal(query)})"
        return "dot", f".loc[lambda {lam}: {render_expr(op.expr, texts, lam)}]"  # type: ignore[arg-type]
    value = f"lambda {lam}: {render_expr(op.expr, texts, lam)}"  # type: ignore[arg-type]
    return "dot", f".assign({keyword_arg(op.key, value)})"  # setitem with a string key


def _flat(chain: Chain) -> str:
    head, steps = chain
    return head + "".join(text for _, text in steps)


def _statement(name: str, chain: Chain) -> str:
    head, steps = chain
    flat = f"{name} = {_flat(chain)}"
    if len(flat) <= MAX_LINE or sum(kind == "dot" for kind, _ in steps) <= 1:
        return flat
    rows = [head]
    for i, (kind, text) in enumerate(steps):
        if kind == "sub" or i == 0:  # the first step stays on the head's line
            rows[-1] += text
        else:
            rows.append(text)
    body = "\n".join(f"    {row}" for row in rows)
    return f"{name} = (\n{body}\n)"


def chained_lines(session: Any, targets: list[str], style: CodeStyle) -> list[str]:
    """Statements (unstyled) that create every node in ``targets``, chaining where possible."""
    names = session.variable_names()
    wanted: set[str] = set()
    for target in targets:
        wanted.update(session.lineage(target))
    ids = [nid for nid in session.node_ids() if nid in wanted]
    ops = {nid: session.node(nid).op for nid in ids}
    consumers: dict[str, list[str]] = {nid: [] for nid in ids}
    for nid, op in ops.items():
        for parent in op.parents() if op is not None else ():
            if parent in consumers and nid not in consumers[parent]:
                consumers[parent].append(nid)

    def inline(nid: str) -> bool:
        op = ops[nid]
        if op is None or nid in targets or len(consumers[nid]) != 1:
            return False
        if op.kind != "func" and not _chainable(op):
            return False
        consumer = ops[consumers[nid][0]]
        return consumer.target != nid or _chainable(consumer)

    lam = unique_name("df", set(names.values()))
    texts = dict(names)
    chains: dict[str, Chain] = {}
    lines: list[str] = []
    for nid in ids:
        node = session.node(nid)
        op = ops[nid]
        if op is None:
            line = root_line(node, "origin")
            if line:
                lines.append(line)
            chains[nid] = (node.name, [])
            continue
        if op.kind == "func":
            chain: Chain = (f"pd.{op.name}({_arglist(op.args, op.kwargs, texts, lam)})", [])
        elif _chainable(op):
            base = chains[op.target] if inline(op.target) else (names[op.target], [])  # type: ignore[index]
            chain = (base[0], [*base[1], _step(op, texts, lam, style)])
        else:
            lines.append(render_op(op, node.name, texts, style).display)
            chains[nid] = (node.name, [])
            continue
        if inline(nid):
            chains[nid] = chain
            texts[nid] = _flat(chain)
            continue
        lines.append(_statement(node.name, chain))
        chains[nid] = (node.name, [])
    return lines
