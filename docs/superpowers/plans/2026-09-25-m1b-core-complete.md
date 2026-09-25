# M1b — Núcleo completo · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Python core: every code style the preferences offer, a workbench history (undo/redo of create, delete, rename, edit-as-new), cancellation and retry, size guards, a memory-bounded result cache, the generated pandas catalog, session export to `.py`/`.ipynb`, and autosave with `fl.open()` — each proven by tests, with the few UI hooks needed to reach them.

**Architecture:** Display code is still produced per op by `codegen.render`, now parameterised by a `CodeStyle` built from `fl.options`; a token-level `restyle()` applies quotes and import aliases, `codegen.query` writes `DataFrame.query` strings, and `codegen.chain` folds single-use steps into chained expressions. The executed form never changes. `Session` gains a `History` of changes, a `ResultCache` (bytes + LRU + pins, freed nodes recompute on demand), guards evaluated before running an op, and cancellation flags. A build-time tool distils pandas' API reference, signatures and runtime probes into `catalog/pandas.json.gz`, read at runtime by `framelab.catalog`. `codegen.export` writes whole sessions; `session.autosave` persists documents in the background.

**Tech Stack:** Python 3.11–3.14, pandas 3.0.6, matplotlib 3.11.2, pyarrow 25, psutil, platformdirs, numpydoc + nbformat (dev only); React/TypeScript only for small workbench hooks.

**Spec:** `docs/superpowers/specs/2026-09-23-framelab-design.md` (sections "Motor pandas, catálogo y codegen", "Workbench", "Sesiones y recetas", "Preferencias"); spike decisions in `docs/superpowers/spikes/2026-09-23-m0-spikes.md` (S3 string aggregations, S6 census, S11 copy semantics).

## Global Constraints

- Python ≥ 3.11 syntax; ruff clean (`target-version = "py311"`, line length 100); `ruff format`.
- Nodes are immutable: an op never changes after creation; "edit" creates a sibling; never pass `inplace`; executed code never mutates a parent.
- The executed form of an op never depends on the code style. Every displayed variant must give a result identical to the executed one, proven by executing the displayed code in tests.
- Generated code only references `pd`, `np`, `datetime`, `decimal` (plus `plt` in figure code) and node variable names; framelab never executes displayed code, only the validated executed form.
- Node ids `n1, n2, …` are never reused within a session, except when undo/redo restores the very node that had that id.
- Session documents never contain code or data (ops, names, specs, source descriptions only).
- Test policy (user decision): Python TDD and strong fidelity tests; frontend: no unit tests, at most extend the existing E2E scripts.
- Commits straight to `main`, each ending with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01Ks8wJ6dnQ283WhqQErFFQG`.
- Every push to `main` publishes to PyPI when the package changed (CI `publish` job): keep CI green.

## Review Focus

1. **Undo/redo interleaved with deletes, renames and edit-as-new** — ids, names, figure layers and values must come back exactly; redo after a new action is impossible. Pinned in Task 4 (`test_undo_redo_survive_mixed_changes`).
2. **A node evicted from the cache while a child is queued or a table window is being read** — the child computes and the window is served, recomputing transparently; never a `KeyError`. Pinned in Task 8 (`test_evicted_parent_is_recomputed_for_a_queued_child`).
3. **Awkward labels under every code style** (spaces, quotes, keywords, non-string column keys, NaN literals) — query/assign/chained fall back to the canonical form instead of producing wrong or invalid code. Pinned in Tasks 1 and 2 (`test_styles_fall_back_on_awkward_labels`).
4. **Cancelling a node other nodes wait for** — waiters get `NodeError`, children become `blocked`, retry heals the whole branch. Pinned in Task 5 (`test_waiters_of_a_cancelled_node_get_node_error`).
5. **Autosave failing** (read-only directory, disk full) or firing mid-computation — the session keeps working and the failure is only logged. Pinned in Task 11 (`test_autosave_failures_never_break_the_session`).

## File map

```
src/framelab/codegen/style.py        CodeStyle (from fl.options), restyle(), import_lines()
src/framelab/codegen/query.py        to_query(): filter expression -> DataFrame.query string or None
src/framelab/codegen/chain.py        chained_lines(): chained code style
src/framelab/codegen/render.py       (modify) style-aware render_op, NegE/NpCall unchanged
src/framelab/codegen/script.py       (modify) styles, root_line(), used_modules()
src/framelab/codegen/export.py       session_script(), session_notebook()
src/framelab/naming.py               (modify) op_alias(), trail-aware auto_node_name()
src/framelab/ops/op.py               (modify) remap_op()
src/framelab/engine/guards.py        GuardError, estimates (merge, get_dummies, explode, pivot_table, crosstab), string-aggregation guard
src/framelab/engine/cache.py         value_bytes(), ResultCache
src/framelab/session/history.py      NodeRecord, Change, History
src/framelab/session/node.py         (modify) CANCELLED/FREED states, alias, force, cancel_requested
src/framelab/session/core.py         (modify) style, rename, history, cancel/retry/clear, edit_as_new, guards, cache
src/framelab/session/figures.py      (modify) style-aware code, names(), set_spec(), figure_display()
src/framelab/session/document.py     (modify) force flags
src/framelab/session/autosave.py     Autosaver, default_directory(), recent(), latest()
src/framelab/catalog/__init__.py     Catalog, Member, Param, load()
src/framelab/catalog/pandas.json.gz  generated (committed)
tools/gen_catalog.py                 build-time generator
src/framelab/api.py                  (modify) _show(), open(), autosaves()
src/framelab/options.py              (modify) performance.* and general.autosave options
src/framelab/protocol/schema.py      (modify) states, cancelling, HistoryInfo
src/framelab/transport/methods.py    (modify) rename, undo/redo, cancel/retry/clear, edit_as_new, pins, export, catalog
frontend/src/...                     undo/redo, cancel/retry/rename, clear errors, export buttons, pins, force apply
tests/test_code_style.py, test_chain.py, test_history.py, test_cancel.py, test_edit_as_new.py,
tests/test_guards.py, test_cache.py, test_catalog.py, test_export.py, test_autosave.py (+ updates)
```

Code blocks that carry a `<!-- file: path -->` marker hold the complete content of that file.

---

### Task 1: Code styles — quotes, aliases, query filters, assign

**Files:**
- Create: `src/framelab/codegen/style.py`, `src/framelab/codegen/query.py`, `tests/test_code_style.py`
- Modify: `src/framelab/codegen/render.py` (`render_op`), `src/framelab/codegen/script.py`, `src/framelab/session/core.py` (`code_style`, `code`, `preview`), `src/framelab/session/figures.py` (`code`)

**Interfaces:**
- Produces: `CodeStyle` (fields `quote`, `pandas_alias`, `numpy_alias`, `pyplot_alias`, `filter_style`, `column_assign`, `chained`, `include_imports`; `from_options(options)`, `aliases`, `safe_for(names)`), `DEFAULT_STYLE`, `restyle(code, style) -> str`, `import_lines(used: set[str], style) -> list[str]`, `to_query(expr) -> str | None`, `render_op(op, result, names, style=DEFAULT_STYLE) -> Rendered`, `keyword_arg(key: str, value: str) -> str` (in render.py), `used_modules(body) -> set[str]`, `root_line(node, mode) -> str | None`, `pipeline_lines(session, ids, mode="origin", style=DEFAULT_STYLE)`, `node_script(session, key, mode="origin", style=None)`, `Session.code_style() -> CodeStyle`, `Session.code(key, mode="origin", style=None)`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/test_code_style.py -->
```python
"""Every code style the preferences offer reproduces the node exactly."""

import math

import pytest
from test_fidelity import CASES, _resolve, assert_same, make_frames

from framelab.codegen.query import to_query
from framelab.codegen.style import CodeStyle, import_lines, restyle
from framelab.naming import RootSpec
from framelab.ops.build import and_, call, col, eq, gt, method, mul, not_, or_, setcol, where
from framelab.options import build_default_registry
from framelab.session import Session

STYLES = {
    "query": {"code.filter_style": "query"},
    "assign": {"code.column_assign": "assign"},
    "single+aliases": {"code.quote": "single", "code.pandas_alias": "pandas", "code.numpy_alias": "numpy"},
}


def session_with(options, *roots):
    registry = build_default_registry()
    for key, value in options.items():
        registry.set(key, value)
    return Session(list(roots), registry)


def test_restyle_renames_modules_and_quotes():
    code = 'x = pd.Series(np.arange(3))\ny = x.str.replace("a", "b")\nz = df.pd\n# pd stays in comments'
    style = CodeStyle(quote="single", pandas_alias="pandas", numpy_alias="numpy")
    assert restyle(code, style) == (
        "x = pandas.Series(numpy.arange(3))\ny = x.str.replace('a', 'b')\nz = df.pd\n# pd stays in comments"
    )


def test_single_quotes_keep_strings_that_contain_one():
    assert restyle('s = "it\'s"', CodeStyle(quote="single")) == 's = "it\'s"'


def test_import_lines_follow_aliases():
    style = CodeStyle(pandas_alias="pandas")
    assert import_lines({"pd", "np", "plt"}, style) == [
        "import matplotlib.pyplot as plt",
        "import pandas",
        "import numpy as np",
    ]


def test_invalid_or_clashing_aliases_fall_back():
    registry = build_default_registry()
    registry.set("code.pandas_alias", "np")  # would clash with numpy
    assert CodeStyle.from_options(registry).aliases == {"pd": "pd", "np": "np", "plt": "plt"}
    registry.set("code.pandas_alias", "1x")
    assert CodeStyle.from_options(registry).pandas_alias == "pd"
    style = CodeStyle(pandas_alias="pandas")
    assert style.safe_for({"pandas", "ventas"}).pandas_alias == "pd"


@pytest.mark.parametrize(
    ("expr", "query"),
    [
        (gt(col("monto"), 100), "monto > 100"),
        (and_(eq(col("pais"), "AR"), gt(col("monto"), 100)), "pais == 'AR' and monto > 100"),
        (
            or_(and_(eq(col("pais"), "AR"), gt(col("monto"), 100)), not_(eq(col("pais"), "UY"))),
            "(pais == 'AR' and monto > 100) or not (pais == 'UY')",
        ),
        (method(col("pais"), "isin", ["UY", "BR"]), "pais in ['UY', 'BR']"),
        (gt(col("precio unitario"), 3), "`precio unitario` > 3"),
        (gt(col("class"), 3), "`class` > 3"),
        (gt(col("monto"), col("cantidad")), "monto > cantidad"),
        (method(col("monto"), "notna"), None),
        (eq(col("pais"), "it's"), None),
        (gt(col("monto"), math.nan), None),
        (gt(col(2024), 1), None),
    ],
)
def test_to_query(expr, query):
    assert to_query(expr) == query


@pytest.mark.parametrize("style", list(STYLES))
@pytest.mark.parametrize("case", list(CASES))
def test_every_style_reproduces_the_node(style, case):
    ventas, clientes = make_frames()
    s = session_with(STYLES[style], RootSpec("ventas", ventas), RootSpec("clientes", clientes))
    try:
        ids = []
        for op in CASES[case]:
            ids.append(s.apply(_resolve(op, ids)).id)
        value = s.wait(ids[-1])
        script = s.code(ids[-1])
        name = s.node(ids[-1]).name
    finally:
        s.close()
    fresh_ventas, fresh_clientes = make_frames()
    namespace = {"ventas": fresh_ventas, "clientes": fresh_clientes}
    exec(script, namespace)  # noqa: S102 - framelab-generated display code under test
    assert_same(value, namespace[name])


def test_query_and_assign_display_forms():
    ventas, _ = make_frames()
    s = session_with({"code.filter_style": "query", "code.column_assign": "assign"}, RootSpec("ventas", ventas))
    try:
        filt = s.apply(where("n1", and_(eq(col("pais"), "AR"), gt(col("monto"), 100))))
        assert s.code(filt.id, mode="step") == "ventas_filt = ventas.query(\"pais == 'AR' and monto > 100\")"
        total = s.apply(setcol("n1", "total", mul(col("monto"), col("cantidad"))))
        assert s.code(total.id, mode="step") == 'ventas_2 = ventas.assign(total=ventas["monto"] * ventas["cantidad"])'
        spaced = s.apply(setcol("n1", "precio final", mul(col("monto"), 2)))
        assert 'ventas.assign(**{"precio final": ventas["monto"] * 2})' in s.code(spaced.id, mode="step")
        notna = s.apply(where("n1", method(col("monto"), "notna")))
        assert s.code(notna.id, mode="step").startswith("# query() cannot express this condition")
        preview = s.preview(where("n1", gt(col("monto"), 1)))
        assert preview["code"] == 'ventas_filt_3 = ventas.query("monto > 1")'
    finally:
        s.close()


def test_styles_fall_back_on_awkward_labels():
    """Review focus 3: non-string keys, quotes and NaN stay faithful under every style."""
    ventas, _ = make_frames()
    ventas[7] = ventas["cantidad"] * 2
    options = {"code.filter_style": "query", "code.column_assign": "assign", "code.quote": "single"}
    s = session_with(options, RootSpec("ventas", ventas))
    try:
        ops = [
            setcol("n1", 8, mul(col(7), 2)),  # int key: assign(**{8: ...}) is invalid -> copy form
            where("n1", eq(col("pais"), 'O"Neil')),
            where("n1", gt(col("monto"), math.nan)),
            call("n1", "rename", columns={"monto": "it's"}),
        ]
        for op in ops:
            node = s.apply(op)
            value = s.wait(node.id)
            fresh = make_frames()[0]
            fresh[7] = fresh["cantidad"] * 2
            namespace = {"ventas": fresh}
            exec(s.code(node.id), namespace)  # noqa: S102
            assert_same(value, namespace[node.name])
    finally:
        s.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_code_style.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'framelab.codegen.query'`

- [ ] **Step 3: Write `style.py` and `query.py`**

<!-- file: src/framelab/codegen/style.py -->
```python
"""How displayed code is written: quotes, import aliases, filters, column assignment, chaining.

Only the displayed code changes. The executed form stays canonical, and the fidelity tests prove
every style gives the same result (spec: "forma equivalente verificada").
"""

from __future__ import annotations

import ast
import io
import keyword
import tokenize
from dataclasses import dataclass, replace
from typing import Any

__all__ = ["DEFAULT_STYLE", "CodeStyle", "import_lines", "restyle"]

_STANDARD = {"pd": "pd", "np": "np", "plt": "plt"}
_MODULES = {"pd": "pandas", "np": "numpy", "plt": "matplotlib.pyplot"}
_IMPORT_ORDER = ("plt", "pd", "np", "datetime", "decimal")


def _alias(value: Any, default: str) -> str:
    ok = isinstance(value, str) and value.isidentifier() and not keyword.iskeyword(value)
    return value if ok else default


@dataclass(frozen=True)
class CodeStyle:
    quote: str = "double"  # double | single
    pandas_alias: str = "pd"
    numpy_alias: str = "np"
    pyplot_alias: str = "plt"
    filter_style: str = "mask"  # mask | query
    column_assign: str = "copy"  # copy | assign
    chained: bool = False
    include_imports: bool = True

    @classmethod
    def from_options(cls, options: Any) -> CodeStyle:
        aliases = (
            _alias(options.get("code.pandas_alias"), "pd"),
            _alias(options.get("code.numpy_alias"), "np"),
            _alias(options.get("code.pyplot_alias"), "plt"),
        )
        if len(set(aliases)) < len(aliases):  # two modules cannot share a name
            aliases = ("pd", "np", "plt")
        return cls(
            quote=options.get("code.quote"),
            pandas_alias=aliases[0],
            numpy_alias=aliases[1],
            pyplot_alias=aliases[2],
            filter_style=options.get("code.filter_style"),
            column_assign=options.get("code.column_assign"),
            chained=options.get("code.style") == "chained",
            include_imports=options.get("code.include_imports"),
        )

    @property
    def aliases(self) -> dict[str, str]:
        return {"pd": self.pandas_alias, "np": self.numpy_alias, "plt": self.pyplot_alias}

    def safe_for(self, names: set[str]) -> CodeStyle:
        """This style, with the standard aliases if a custom one would shadow a variable."""
        custom = {a for k, a in self.aliases.items() if a != _STANDARD[k]}
        if custom & names:
            return replace(self, pandas_alias="pd", numpy_alias="np", pyplot_alias="plt")
        return self


DEFAULT_STYLE = CodeStyle()


def import_lines(used: set[str], style: CodeStyle = DEFAULT_STYLE) -> list[str]:
    """``import`` statements for the canonical module names in ``used``."""
    out = []
    for key in _IMPORT_ORDER:
        if key not in used:
            continue
        if key in _MODULES:
            module, alias = _MODULES[key], style.aliases[key]
            out.append(f"import {module}" if alias == module else f"import {module} as {alias}")
        else:
            out.append(f"import {key}")
    return out


def _single(token: str) -> str:
    if not token or token[0] not in "'\"" or token[:3] in ('"""', "'''"):
        return token  # prefixed or triple-quoted strings stay as they are
    value = ast.literal_eval(token)
    return repr(value) if isinstance(value, str) else token


def restyle(code: str, style: CodeStyle = DEFAULT_STYLE) -> str:
    """Apply the quote and import-alias preferences to framelab-generated display code."""
    renames = {k: v for k, v in style.aliases.items() if k != v}
    if style.quote != "single" and not renames:
        return code
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, SyntaxError):
        return code
    edits: list[tuple[tuple[int, int], tuple[int, int], str]] = []
    for i, tok in enumerate(tokens):
        if tok.type == tokenize.NAME and tok.string in renames:
            after = tokens[i + 1] if i + 1 < len(tokens) else None
            before = tokens[i - 1] if i else None
            attribute = before is not None and before.string == "."
            if after is not None and after.string == "." and not attribute:
                edits.append((tok.start, tok.end, renames[tok.string]))
        elif tok.type == tokenize.STRING and style.quote == "single":
            new = _single(tok.string)
            if new != tok.string:
                edits.append((tok.start, tok.end, new))
    lines = code.splitlines(keepends=True)
    for (row, col), (end_row, end_col), text in reversed(edits):
        if row == end_row:
            line = lines[row - 1]
            lines[row - 1] = line[:col] + text + line[end_col:]
    return "".join(lines)
```

<!-- file: src/framelab/codegen/query.py -->
```python
"""Write a filter condition as a ``DataFrame.query`` string when query() can express it."""

from __future__ import annotations

import keyword
import math
from typing import Any

from ..ops.values import BoolE, CallE, Cmp, GetCol, ListV, Lit, NotE, This

__all__ = ["to_query"]


class _NoQuery(Exception):
    pass


def _column(e: Any) -> str:
    if not (isinstance(e, GetCol) and isinstance(e.base, This) and isinstance(e.label, str)):
        raise _NoQuery
    label = e.label
    if label.isidentifier() and not keyword.iskeyword(label) and label != "index":
        return label
    if not label or any(c in label for c in "`\n\\"):
        raise _NoQuery
    return f"`{label}`"


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return repr(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, str) and not any(c in value for c in "'\"\\\n`@"):
        return f"'{value}'"
    raise _NoQuery


def _operand(v: Any) -> str:
    if isinstance(v, GetCol):
        return _column(v)
    if isinstance(v, Lit):
        return _literal(v.value)
    raise _NoQuery


def _items(v: Any) -> list[Any]:
    if isinstance(v, ListV):
        return list(v.items)
    if isinstance(v, Lit) and isinstance(v.value, (list, tuple)):
        return [Lit(x) for x in v.value]
    raise _NoQuery


def _q(e: Any) -> str:
    if isinstance(e, Cmp):
        return f"{_column(e.left)} {e.op} {_operand(e.right)}"
    if isinstance(e, BoolE):
        parts = [f"({_q(i)})" if isinstance(i, BoolE) else _q(i) for i in e.items]
        return f" {e.op} ".join(parts)
    if isinstance(e, NotE):
        return f"not ({_q(e.item)})"
    simple_call = isinstance(e, CallE) and not e.accessor and not e.kwargs and len(e.args) == 1
    if simple_call and e.name == "isin":
        items = _items(e.args[0])
        if not items:
            raise _NoQuery
        return f"{_column(e.base)} in [{', '.join(_operand(i) for i in items)}]"
    raise _NoQuery


def to_query(expr: Any) -> str | None:
    """The query() text for ``expr``, or None when only a boolean mask can express it."""
    try:
        return _q(expr)
    except _NoQuery:
        return None
```

- [ ] **Step 4: Make `render_op` style-aware** — in `src/framelab/codegen/render.py` add imports and replace `render_op`:

```python
import keyword

from .query import to_query
from .style import DEFAULT_STYLE, CodeStyle


def keyword_arg(key: str, value: str) -> str:
    """``key=value`` when ``key`` is a valid keyword, else ``**{"key": value}``."""
    if key.isidentifier() and not keyword.iskeyword(key):
        return f"{key}={value}"
    return f"**{{{emit_literal(key)}: {value}}}"


def render_op(
    op: Op, result: str, names: Mapping[str, str], style: CodeStyle = DEFAULT_STYLE
) -> Rendered:
    """Statement(s) that bind ``result``; the executed form is a verified equivalent."""
    if op.kind == "setitem":
        base = names[op.target]  # type: ignore[index]
        value = render_expr(op.expr, names, result)  # type: ignore[arg-type]
        assign = f"{result}[{emit_literal(op.key)}] = {value}"
        # Copy-on-Write: copy(deep=False) is equal and O(1); the user sees the idiom.
        executed = f"{result} = {base}.copy(deep=False)\n{assign}"
        if style.column_assign == "assign" and isinstance(op.key, str):
            arg = keyword_arg(op.key, render_expr(op.expr, names, base))  # type: ignore[arg-type]
            return Rendered(f"{result} = {base}.assign({arg})", executed)
        return Rendered(f"{result} = {base}.copy()\n{assign}", executed)
    code = f"{result} = {_expression(op, names)}"
    if op.kind == "filter" and style.filter_style == "query":
        query = to_query(op.expr)
        if query is not None:
            base = names[op.target]  # type: ignore[index]
            return Rendered(f"{result} = {base}.query({emit_literal(query)})", code)
        return Rendered(f"# query() cannot express this condition: boolean mask\n{code}", code)
    return Rendered(code, code)
```

Add `"keyword_arg"` to `__all__`.

- [ ] **Step 5: Styles in scripts** — replace the body of `src/framelab/codegen/script.py` below the imports with:

```python
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
```

(`chain.py` arrives in Task 2; until then `style.chained` is never true in tests.)

- [ ] **Step 6: Session and figures use the style** — in `src/framelab/session/core.py`:

```python
from ..codegen.style import CodeStyle, restyle

    def code_style(self) -> CodeStyle:
        """The code style from ``fl.options``, never shadowing a node's variable."""
        return CodeStyle.from_options(self._options).safe_for(set(self.names))

    def code(self, key: str, mode: str = "origin", style: CodeStyle | None = None) -> str:
        from ..codegen.script import node_script

        return node_script(self, key, mode=mode, style=style)
```

and in `preview` replace the returned code with
`"code": restyle(render_op(op, final, names, style).display, style)` where `style = self.code_style()`.

In `src/framelab/session/figures.py` `code()`: take `style = self._session.code_style()`, build the pipeline with `pipeline_lines(self._session, order, style=style)` (or `chained_lines` when `style.chained`, Task 2), restyle pipeline and figure code, and compute imports as
`import_lines(used_modules(pipeline + "\n" + figure) | {"plt", "pd"}, style)` (only when `style.include_imports`). Replace the old `used_imports` import with `used_modules`/`import_lines`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_code_style.py tests/test_fidelity.py tests/test_render.py tests/test_plot.py -q`
Expected: PASS (fix any display-string expectation in older tests only if it encodes the old unstyled path).

- [ ] **Step 8: Commit**

```bash
git add src/framelab/codegen tests/test_code_style.py src/framelab/session
git commit -m "Code styles: quotes, import aliases, query filters and assign, all proven faithful"
```

---

### Task 2: Chained code style

**Files:**
- Create: `src/framelab/codegen/chain.py`, `tests/test_chain.py`
- Modify: `src/framelab/session/figures.py` (`code` uses `chained_lines` when `style.chained`)

**Interfaces:**
- Consumes: `CodeStyle`, `keyword_arg`, `to_query`, `root_line`, `render_op`, `_arglist`, `_accessor`, `render_expr` (Task 1 / existing render.py).
- Produces: `chained_lines(session, targets: list[str], style: CodeStyle) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/test_chain.py -->
```python
"""Chained style: single-use steps fold into one expression, and the code stays faithful."""

import pytest
from test_fidelity import CASES, _resolve, assert_same, make_frames

from framelab.naming import RootSpec
from framelab.ops.build import call, col, func, getitem, gt, mul, node, ref_col, setcol, where
from framelab.options import build_default_registry
from framelab.session import Session


def chained_session():
    registry = build_default_registry()
    registry.set("code.style", "chained")
    ventas, clientes = make_frames()
    return Session([RootSpec("ventas", ventas), RootSpec("clientes", clientes)], registry)


@pytest.mark.parametrize("case", list(CASES))
def test_chained_code_reproduces_the_node(case):
    s = chained_session()
    try:
        ids = []
        for op in CASES[case]:
            ids.append(s.apply(_resolve(op, ids)).id)
        value, script, name = s.wait(ids[-1]), s.code(ids[-1]), s.node(ids[-1]).name
    finally:
        s.close()
    ventas, clientes = make_frames()
    namespace = {"ventas": ventas, "clientes": clientes}
    exec(script, namespace)  # noqa: S102 - framelab-generated display code under test
    assert_same(value, namespace[name])


def test_a_pipeline_becomes_one_chained_expression():
    s = chained_session()
    try:
        a = s.apply(where("n1", gt(col("monto"), 50)))
        b = s.apply(setcol(a.id, "total", mul(col("monto"), col("cantidad"))))
        c = s.apply(call(b.id, "groupby", by=ref_col("pais")))
        d = s.apply(getitem(c.id, "total"))
        e = s.apply(call(d.id, "sum"))
        f = s.apply(call(e.id, "sort_values", ascending=False), name="ranking")
        assert s.code(f.id) == (
            "import pandas as pd\n\n"
            "# ventas: the DataFrame (6 × 7) passed to fl.explore()\n"
            "ranking = (\n"
            '    ventas.loc[lambda df: df["monto"] > 50]\n'
            '    .assign(total=lambda df: df["monto"] * df["cantidad"])\n'
            '    .groupby(by="pais")["total"]\n'
            "    .sum()\n"
            "    .sort_values(ascending=False)\n"
            ")\n"
        )
    finally:
        s.close()


def test_branch_points_stay_variables_and_arguments_inline():
    s = chained_session()
    try:
        x = s.apply(where("n1", gt(col("monto"), 50)))
        y = s.apply(call(x.id, "head", n=2))
        z = s.apply(call(x.id, "tail", n=2))
        w = s.apply(func("concat", objs=[node(y.id), node(z.id)]), name="extremos")
        code = s.code(w.id)
        assert 'ventas_filt = ventas.loc[lambda df: df["monto"] > 50]' in code
        assert "extremos = pd.concat(objs=[ventas_filt.head(n=2), ventas_filt.tail(n=2)])" in code
    finally:
        s.close()


def test_int_keys_break_the_chain_but_stay_faithful():
    s = chained_session()
    try:
        a = s.apply(call("n1", "head", n=3))
        b = s.apply(setcol(a.id, 5, mul(col("monto"), 2)))
        c = s.apply(call(b.id, "tail", n=1))
        code, value, name = s.code(c.id), s.wait(c.id), s.node(c.id).name
        assert "ventas_head_2 = ventas.head(n=3).copy()" not in code  # a statement, not a chain
    finally:
        s.close()
    namespace = {"ventas": make_frames()[0], "clientes": make_frames()[1]}
    exec(code, namespace)  # noqa: S102
    assert_same(value, namespace[name])
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_chain.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'framelab.codegen.chain'`

- [ ] **Step 3: Implement**

<!-- file: src/framelab/codegen/chain.py -->
```python
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
```

In `src/framelab/session/figures.py` `code()`, build the pipeline as
`chained_lines(self._session, doc.sources(), style)` when `style.chained`, else the existing `pipeline_lines` call.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_chain.py tests/test_code_style.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/framelab/codegen/chain.py tests/test_chain.py src/framelab/session/figures.py
git commit -m "Chained code style with branch points kept as variables"
```

---

### Task 3: Names — root + last aliases, and renaming

**Files:**
- Modify: `src/framelab/naming.py`, `src/framelab/session/node.py` (`alias` field), `src/framelab/session/core.py` (`_trail`, `rename`), `src/framelab/session/figures.py` (`names()`), `src/framelab/transport/methods.py` (`node.rename`), `tests/test_node_names.py`
- Create: `tests/test_rename.py`

**Interfaces:**
- Produces: `op_alias(op, names) -> str` (`""` for setitem), `auto_node_name(op, names, taken, trail: Sequence[str] = ()) -> str`, `Node.alias: str`, `Session._trail(nid) -> tuple[str, ...]`, `Session.rename(key, new_name) -> list[str]` (ids renamed), `NameTaken` (code `name_taken`), `CannotRename` (code `cannot_rename`), `FigureStore.names() -> set[str]`, protocol `node.rename {id, name}` → `{"renamed": [ids]}`.

- [ ] **Step 1: Update the naming test and write rename tests**

In `tests/test_node_names.py` replace `test_long_chains_restart_from_the_root` with:

```python
def test_long_names_keep_the_root_and_the_last_steps():
    names = {"n9": "ventas_filt_2_by_pais_total"}
    trail = ("ventas", "filt", "by_pais", "total")
    got = auto_node_name(call("n9", "sum"), names, set(names.values()), trail)
    assert got == "ventas_total_sum"


def test_very_long_aliases_fall_back_to_root_and_alias():
    names = {"n9": "ventas_" + "x" * 25}
    trail = ("ventas", "x" * 25)
    got = auto_node_name(call("n9", "drop_duplicates"), names, set(names.values()), trail)
    assert got == "ventas_dedup" and len(got) <= 30
```

<!-- file: tests/test_rename.py -->
```python
import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call, node, ref_col
from framelab.session import Session
from framelab.session.core import CannotRename, NameTaken


@pytest.fixture
def s():
    ventas = pd.DataFrame({"pais": ["AR", "UY"], "monto": [1.0, 2.0]})
    clientes = pd.DataFrame({"pais": ["AR"], "nombre": ["Ana"]})
    session = Session([RootSpec("ventas", ventas), RootSpec("clientes", clientes)])
    yield session
    session.close()


def test_auto_named_children_follow_a_rename(s):
    head = s.apply(call("n1", "head", n=1))
    sorted_ = s.apply(call(head.id, "sort_values", by=ref_col("monto")))
    kept = s.apply(call(head.id, "tail", n=1), name="mi_tabla")
    assert s.rename(head.id, "top") == [head.id, sorted_.id]
    assert s.node(sorted_.id).name == "top_sorted"
    assert s.node(kept.id).name == "mi_tabla"  # edited names never follow
    assert "top_sorted = top.sort_values(" in s.code(sorted_.id)
    assert not s.node(head.id).name_auto


def test_labels_that_mention_a_renamed_node_update(s):
    merged = s.apply(call("n1", "merge", node("n2"), on="pais"))
    head = s.apply(call("n2", "head", n=1))
    merged2 = s.apply(call("n1", "merge", node(head.id), on="pais"))
    s.rename(head.id, "primeros")
    assert s.node(merged2.id).label == "merge(primeros, on=\"pais\")"
    assert s.node(merged2.id).name == "ventas_primeros"
    assert s.node(merged.id).name == "ventas_clientes"


def test_rename_rules(s):
    head = s.apply(call("n1", "head", n=1))
    with pytest.raises(CannotRename):
        s.rename("n1", "otra")
    with pytest.raises(NameTaken):
        s.rename(head.id, "clientes")
    assert s.rename(head.id, "1 raro!") == [head.id]
    assert s.node(head.id).name == "df_1_raro"
```

(If `op_label` renders merge differently, adjust only the expected label text to what `op_label` produces for `call("n1", "merge", node(x), on="pais")` — the assertion is that it mentions the new name.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_rename.py tests/test_node_names.py -q`
Expected: FAIL (`ImportError: cannot import name 'CannotRename'`, and the new naming expectations)

- [ ] **Step 3: Implement naming** — in `src/framelab/naming.py` replace `auto_node_name` with:

```python
def op_alias(op: Any, names: Mapping[str, str]) -> str:
    """The short word an op adds to a name (``""`` for setitem: it keeps its parent's name)."""
    if op.kind == "setitem":
        return ""
    if op.kind == "getitem":
        return "cols" if isinstance(op.key, list) else _slug(label_text(op.key))
    if op.kind == "filter":
        return "filt"
    if op.kind == "call" and op.name == "groupby" and op.kwargs:
        by = dict(op.kwargs).get("by")
        return "by_" + _slug(label_text(_first_label(by))) if by is not None else "grouped"
    if op.kind == "call" and op.name == "merge" and op.args and hasattr(op.args[0], "id"):
        return names[op.args[0].id]
    return OP_ALIASES.get(op.name, op.name)


def auto_node_name(
    op: Any, names: Mapping[str, str], taken: Iterable[str], trail: Sequence[str] = ()
) -> str:
    """``{parent}_{alias}``, short, unique and a valid identifier.

    Past MAX_NAME the name keeps the root and the last steps: ``trail`` is the parent's
    ``(root, alias, alias, …)``; without it the root is the parent name's first word.
    """
    taken = set(taken)
    if op.target is not None:
        parent = names[op.target]
    else:
        refs = op.parents()
        parent = names[refs[0]] if refs else DEFAULT_ROOT_NAME
    if op.kind == "setitem":
        return unique_name(parent, taken)
    alias = op_alias(op, names)
    base = f"{parent}_{alias}"
    if len(base) > MAX_NAME:
        root = trail[0] if trail else parent.split("_")[0]
        recent = [a for a in trail[1:] if a][-1:]
        for candidate in ("_".join([root, *recent, alias]), f"{root}_{alias}"):
            base = candidate
            if len(base) <= MAX_NAME:
                break
        base = base[:MAX_NAME].rstrip("_")
    return unique_name(sanitize_identifier(base), taken)
```

Add `"op_alias"` to `__all__` and `Sequence` to the `collections.abc` import.

- [ ] **Step 4: Implement trail and rename** — `src/framelab/session/node.py`: add `alias: str = ""` to `Node`. In `src/framelab/session/core.py`:

```python
from ..naming import RootSpec, auto_node_name, op_alias, sanitize_identifier


class NameTaken(FramelabError, ValueError):
    code = "name_taken"


class CannotRename(FramelabError, ValueError):
    code = "cannot_rename"
```

Roots get `alias=spec.name`. In `apply`, compute
`trail = self._trail(op.target) if op.target else ()`, call `auto_node_name(op, names, taken, trail)` and set `alias=op_alias(op, names)` on the new `Node`. Add:

```python
    def _trail(self, nid: str) -> tuple[str, ...]:
        """(root name, alias, alias, …) along the first-parent chain of ``nid``."""
        parts: list[str] = []
        node = self._nodes[nid]
        while not node.is_root:
            if node.alias:
                parts.append(node.alias)
            node = self._nodes[node.parents[0]]
        return (node.name, *reversed(parts))

    def _set_name(self, node: Node, name: str, auto: bool) -> None:
        if self._by_name.get(node.name) == node.id:
            del self._by_name[node.name]
        node.name, node.name_auto = name, auto
        self._by_name[name] = node.id

    def rename(self, key: str, new_name: str) -> list[str]:
        """Rename a node; auto-named descendants follow. Returns the ids whose name changed."""
        with self._lock:
            nid = self._resolve(key)
            node = self._nodes[nid]
            if node.is_root:
                raise CannotRename(f"{node.name} is your own variable: rename it in your code")
            final = sanitize_identifier(new_name)
            taken = (set(self._by_name) | self.plots.names()) - {node.name}
            if final in taken:
                raise NameTaken(f"{final!r} is already used")
            changes: list[tuple[str, str, bool, str, bool]] = []
            if final != node.name or node.name_auto:
                changes.append((nid, node.name, node.name_auto, final, False))
                self._set_name(node, final, False)
            touched = {nid}
            for d in self.descendants(nid)[1:]:
                child = self._nodes[d]
                names = self.variable_names()
                label = op_label(child.op, names)  # type: ignore[arg-type]
                if label != child.label:
                    child.label = label
                    touched.add(d)
                if child.name_auto:
                    others = (set(self._by_name) | self.plots.names()) - {child.name}
                    trail = self._trail(child.op.target) if child.op.target else ()  # type: ignore[union-attr]
                    fresh = auto_node_name(child.op, names, others, trail)
                    if fresh != child.name:
                        changes.append((d, child.name, True, fresh, True))
                        self._set_name(child, fresh, True)
                        touched.add(d)
            if changes or len(touched) > 1:
                self.rev += 1
            self._after_rename(changes)
            infos = [self._nodes[i].info() for i in self._nodes if i in touched]
        for info in infos:
            self._emit("node.upserted", info)
        return [c[0] for c in changes]

    def _after_rename(self, changes: list[tuple[str, str, bool, str, bool]]) -> None:
        """Hook for the history (Task 4)."""
```

`descendants()` already includes nodes that take a renamed node as a `NodeRef` argument, because `parents` lists every referenced node. In `src/framelab/session/figures.py` add:

```python
    def names(self) -> set[str]:
        with self._lock:
            return {d.spec["name"] for d in self._docs.values()}
```

In `src/framelab/transport/methods.py`:

```python
    def rename(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise BadRequest("name must be a non-empty string")
        return {"renamed": session.rename(_id(params), name)}

    dispatcher.register("node.rename", rename)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_rename.py tests/test_node_names.py tests/test_session_graph.py tests/test_document.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/framelab tests/test_rename.py tests/test_node_names.py
git commit -m "Names keep the root and the last steps; renaming with auto-named children following"
```

---

### Task 4: Workbench history — undo/redo of create, delete and rename

**Files:**
- Create: `src/framelab/session/history.py`, `tests/test_history.py`
- Modify: `src/framelab/session/node.py` (`force` field), `src/framelab/session/core.py`, `src/framelab/session/figures.py` (`set_spec`), `src/framelab/protocol/schema.py` (`HistoryInfo`, `SessionSnapshot.history`), `src/framelab/transport/methods.py` (`graph.undo`, `graph.redo`)

**Interfaces:**
- Consumes: `Session.rename` / `_after_rename` hook / `_set_name` (Task 3).
- Produces: `NodeRecord(id, name, name_auto, op, force=False)`, `Change(kind, nodes, figures, names)`, `History.push/take_undo/take_redo/undone/done/info`, `Session.undo() -> bool`, `Session.redo() -> bool`, `Session.batch()` (context manager: one undo step for every node created inside), `Session.delete(*keys) -> {"ids", "figures"}`, `FigureStore.set_spec(fid, spec)`, snapshot key `history: {"can_undo": bool, "can_redo": bool}`, event `graph.history`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/test_history.py -->
```python
import numpy as np
import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops.build import call, ref_col
from framelab.session import Session

VENTAS = pd.DataFrame({"pais": ["AR", "UY", "AR", "BR"], "monto": [10.0, np.nan, 30.0, 5.0]})


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS.copy())])
    yield session
    session.close()


def state(session):
    return [(n.id, n.name, n.name_auto) for n in session.nodes()]


def test_undo_create_and_redo_restores_the_same_node(s):
    head = s.apply(call("n1", "head", n=2))
    s.wait(head.id)
    assert s.snapshot()["history"] == {"can_undo": True, "can_redo": False}
    assert s.undo() and head.id not in s
    assert s.snapshot()["history"] == {"can_undo": False, "can_redo": True}
    assert s.redo()
    assert s.node(head.id).name == "ventas_head" and s.node(head.id).name_auto
    pd.testing.assert_frame_equal(s.wait(head.id), VENTAS.head(2))


def test_undo_delete_restores_nodes_and_figure_layers(s):
    head = s.apply(call("n1", "head", n=3))
    last = s.apply(call(head.id, "tail", n=1), name="ultima")
    fig = s.plots.create(head.id)
    spec = fig["spec"]
    spec["axes"][0]["layers"] = [
        {"kind": "bar", "source": head.id, "x": {"col": "pais"}, "y": [{"col": "monto"}]}
    ]
    s.plots.update(fig["id"], spec)
    s.delete(head.id)
    assert s.plots.get(fig["id"])["spec"]["axes"][0]["layers"] == []
    assert s.undo()
    assert s.node(last.id).name == "ultima" and not s.node(last.id).name_auto
    assert s.plots.get(fig["id"])["spec"]["axes"][0]["layers"][0]["source"] == head.id
    pd.testing.assert_frame_equal(s.wait(last.id), VENTAS.head(3).tail(1))
    assert s.redo() and head.id not in s and last.id not in s


def test_undo_rename_restores_every_name(s):
    head = s.apply(call("n1", "head", n=1))
    srt = s.apply(call(head.id, "sort_values", by=ref_col("monto")))
    s.rename(head.id, "top")
    assert s.undo()
    assert s.node(head.id).name == "ventas_head" and s.node(head.id).name_auto
    assert s.node(srt.id).name == "ventas_head_sorted"
    assert s.redo() and s.node(srt.id).name == "top_sorted"


def test_new_changes_clear_redo(s):
    s.apply(call("n1", "head", n=1))
    s.undo()
    s.apply(call("n1", "tail", n=1))
    assert not s.redo()


def test_batches_are_one_step(s):
    with s.batch():
        a = s.apply(call("n1", "head", n=2))
        b = s.apply(call(a.id, "tail", n=1))
    assert s.undo() and a.id not in s and b.id not in s
    assert not s.undo()


def test_undo_redo_survive_mixed_changes(s):
    """Review focus 1: undo everything, redo everything, same graph and values."""
    a = s.apply(call("n1", "head", n=3))
    b = s.apply(call(a.id, "tail", n=2))
    s.rename(b.id, "cola")
    c = s.apply(call("n1", "tail", n=1))
    s.delete(a.id)
    final = state(s)
    for _ in range(4):
        assert s.undo()
    assert state(s) == [("n1", "ventas", False), (a.id, "ventas_head", True)]
    assert s.undo() and state(s) == [("n1", "ventas", False)]
    assert not s.undo()
    for _ in range(5):
        assert s.redo()
    assert state(s) == final
    pd.testing.assert_frame_equal(s.wait(c.id), VENTAS.tail(1))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_history.py -q`
Expected: FAIL (`KeyError: 'history'` / `AttributeError: 'Session' object has no attribute 'undo'`)

- [ ] **Step 3: Implement the history**

<!-- file: src/framelab/session/history.py -->
```python
"""Workbench history: graph changes that can be undone and redone (last in, first out)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..ops import Op

__all__ = ["Change", "History", "NodeRecord"]

MAX_CHANGES = 200


@dataclass(frozen=True)
class NodeRecord:
    """Everything needed to re-create a node exactly (its value is computed again)."""

    id: str
    name: str
    name_auto: bool
    op: Op
    force: bool = False


@dataclass
class Change:
    kind: str  # create | delete | rename
    nodes: list[NodeRecord] = field(default_factory=list)
    figures: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # specs before
    names: list[tuple[str, str, bool, str, bool]] = field(default_factory=list)


class History:
    def __init__(self, limit: int = MAX_CHANGES) -> None:
        self.limit = limit
        self._undo: list[Change] = []
        self._redo: list[Change] = []

    def push(self, change: Change) -> None:
        self._undo.append(change)
        del self._undo[: -self.limit]
        self._redo.clear()

    def take_undo(self) -> Change | None:
        return self._undo.pop() if self._undo else None

    def take_redo(self) -> Change | None:
        return self._redo.pop() if self._redo else None

    def undone(self, change: Change) -> None:
        self._redo.append(change)

    def done(self, change: Change) -> None:
        self._undo.append(change)

    def info(self) -> dict[str, bool]:
        return {"can_undo": bool(self._undo), "can_redo": bool(self._redo)}
```

In `src/framelab/session/node.py` add `force: bool = False` to `Node`.

In `src/framelab/session/core.py`:

```python
import contextlib

from .history import Change, History, NodeRecord

# in __init__
        self._history = History()
        self._replaying = 0
        self._batch: Change | None = None

    # ---- history -------------------------------------------------------------------------
    @staticmethod
    def _record_of(node: Node) -> NodeRecord:
        return NodeRecord(node.id, node.name, node.name_auto, node.op, node.force)  # type: ignore[arg-type]

    def _record(self, change: Change) -> None:
        if self._replaying:
            return
        if self._batch is not None and change.kind == "create":
            self._batch.nodes.extend(change.nodes)
            return
        self._history.push(change)

    @contextlib.contextmanager
    def batch(self):
        """Every node created inside becomes one undo step."""
        outer = self._batch is None
        if outer:
            self._batch = Change("create")
        try:
            yield
        finally:
            if outer:
                change, self._batch = self._batch, None
                if change is not None and change.nodes:
                    self._history.push(change)

    @contextlib.contextmanager
    def _replay(self):
        self._replaying += 1
        try:
            yield
        finally:
            self._replaying -= 1

    def undo(self) -> bool:
        with self._lock:
            change = self._history.take_undo()
        if change is None:
            return False
        with self._replay():
            self._revert(change)
        with self._lock:
            self._history.undone(change)
        self._emit("graph.history", self._history.info())
        return True

    def redo(self) -> bool:
        with self._lock:
            change = self._history.take_redo()
        if change is None:
            return False
        with self._replay():
            self._reapply(change)
        with self._lock:
            self._history.done(change)
        self._emit("graph.history", self._history.info())
        return True

    def _revert(self, change: Change) -> None:
        if change.kind == "create":
            self._drop([r.id for r in change.nodes])
        elif change.kind == "delete":
            self._restore(change.nodes)
            for fid, spec in change.figures:
                self.plots.set_spec(fid, spec)
        else:
            for nid, old, old_auto, _new, _auto in reversed(change.names):
                self._rename_to(nid, old, old_auto)

    def _reapply(self, change: Change) -> None:
        if change.kind == "create":
            self._restore(change.nodes)
        elif change.kind == "delete":
            self._drop([r.id for r in change.nodes])
        else:
            for nid, _old, _old_auto, new, auto in change.names:
                self._rename_to(nid, new, auto)

    def _drop(self, ids: list[str]) -> None:
        existing = [i for i in ids if i in self._nodes]
        if existing:
            self.delete(*existing)

    def _restore(self, records: list[NodeRecord]) -> None:
        for r in records:
            if r.id in self._nodes:
                continue
            free = r.name not in self._by_name
            node = self.apply(r.op, name=r.name if free else None, node_id=r.id, force=r.force)
            with self._lock:
                node.name_auto = r.name_auto

    def _rename_to(self, nid: str, name: str, auto: bool) -> None:
        with self._lock:
            node = self._nodes.get(nid)
            if node is None:
                return
            if self._by_name.get(name, nid) != nid:
                name = unique_name(name, set(self._by_name))
            self._set_name(node, name, auto)
            names = self.variable_names()
            touched = [node]
            for d in self.descendants(nid)[1:]:
                child = self._nodes[d]
                child.label = op_label(child.op, names)  # type: ignore[arg-type]
                touched.append(child)
            self.rev += 1
            infos = [n.info() for n in touched]
        for info in infos:
            self._emit("node.upserted", info)
```

(`unique_name` joins the `..naming` import.) Then:
- `apply(self, op, *, name=None, node_id=None, force=False)`: store `force` on the new `Node` and, after registering it, call `self._record(Change("create", nodes=[self._record_of(node)]))`.
- `_after_rename(changes)`: `if changes: self._record(Change("rename", names=changes))`.
- Replace `delete(self, key)` with a multi-key version that records the change:

```python
    def delete(self, *keys: str) -> dict[str, Any]:
        """Remove nodes and all their descendants (roots are the input data and stay)."""
        with self._lock:
            starts = [self._resolve(k) for k in keys]
            for nid in starts:
                if self._nodes[nid].is_root:
                    raise CannotDelete(f"{self._nodes[nid].name} is data passed to fl.explore()")
            doomed: set[str] = set()
            for nid in starts:
                doomed.update(self.descendants(nid))
            ids = [i for i in self._nodes if i in doomed]
            records = [self._record_of(self._nodes[i]) for i in ids]
            for i in ids:
                node = self._nodes.pop(i)
                if self._by_name.get(node.name) == i:
                    del self._by_name[node.name]
                self._results.pop(i, None)
                self._encoders.pop(i, None)
                future = self._futures.pop(i, None)
                if future is not None:
                    future.cancel()
            self.rev += 1
        self._emit("node.deleted", {"ids": ids})
        before = {
            f["id"]: self.plots.get(f["id"])["spec"]
            for f in self.plots.infos()
            if set(f["sources"]) & doomed
        }
        figures = self.plots.drop_sources(set(ids))
        self._record(Change("delete", nodes=records, figures=[(f, before[f]) for f in figures]))
        return {"ids": ids, "figures": figures}
```

- `snapshot()` gains `"history": self._history.info()`.

In `src/framelab/session/figures.py`:

```python
    def set_spec(self, fid: str, spec: dict[str, Any]) -> None:
        """Put back a spec (graph undo); the figure's own history is not touched."""
        with self._lock:
            doc = self._docs.get(fid)
            if doc is None:
                return
            doc.spec = normalize(spec, set(self._session.node_ids()))
            doc.version += 1
            self._changed(doc)
```

In `src/framelab/protocol/schema.py`:

```python
class HistoryInfo(TypedDict):
    can_undo: bool
    can_redo: bool
```

and `history: HistoryInfo` in `SessionSnapshot`; regenerate types with `.venv/bin/python tools/gen_ts_types.py`.

In `src/framelab/transport/methods.py`:

```python
    dispatcher.register("graph.undo", lambda params, _b: {"done": session.undo()})
    dispatcher.register("graph.redo", lambda params, _b: {"done": session.redo()})
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_history.py tests/test_session_graph.py tests/test_rename.py tests/test_tsgen.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/framelab tests/test_history.py frontend/src/generated/protocol.ts
git commit -m "Workbench history: undo and redo node creation, deletion and renames"
```

---

### Task 5: Cancel, retry and clear failed nodes

**Files:**
- Create: `tests/test_cancel.py`
- Modify: `src/framelab/session/node.py`, `src/framelab/session/core.py`, `src/framelab/protocol/schema.py` (`NodeStateName`, `NodeInfo.cancelling`), `src/framelab/transport/methods.py`

**Interfaces:**
- Produces: `NodeState.CANCELLED` (`"cancelled"`), `NodeState.FREED` (`"freed"`, used by Task 8), `Node.cancel_requested`, `NodeInfo.cancelling`, `Session.cancel(key) -> bool`, `Session.retry(key) -> list[str]`, `Session.clear_failed() -> {"ids", "figures"}`; protocol `node.cancel {id}` → `{"cancelled"}`, `node.retry {id}` → `{"ids"}`, `graph.clear_failed {}` → `{"ids", "figures"}`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/test_cancel.py -->
```python
import threading

import numpy as np
import pandas as pd
import pytest

import framelab.session.core as core
from framelab.naming import RootSpec
from framelab.ops.build import call, getitem
from framelab.session import NodeError, NodeState, Session

VENTAS = pd.DataFrame({"pais": ["AR", "UY", "AR"], "monto": [10.0, np.nan, 30.0]})


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS.copy())])
    yield session
    session.close()


def block_lane(session):
    gate = threading.Event()
    session._lane.submit(gate.wait, 10)
    return gate


def test_cancel_a_queued_node_blocks_its_children(s):
    gate = block_lane(s)
    a = s.apply(call("n1", "head", n=2))
    b = s.apply(call(a.id, "tail", n=1))
    assert s.cancel(a.id)
    assert s.node(a.id).state is NodeState.CANCELLED
    gate.set()
    with pytest.raises(NodeError):
        s.wait(b.id, timeout=5)
    assert s.node(b.id).state is NodeState.BLOCKED


def test_cancel_a_running_node_discards_its_result(s, monkeypatch):
    started, release = threading.Event(), threading.Event()
    real = core.run_statement

    def slow(code, result, env):
        started.set()
        release.wait(5)
        return real(code, result, env)

    monkeypatch.setattr(core, "run_statement", slow)
    a = s.apply(call("n1", "head", n=2))
    assert started.wait(5)
    assert s.cancel(a.id)
    assert s.node(a.id).info()["cancelling"] is True
    release.set()
    with pytest.raises(NodeError, match="cancelled"):
        s.wait(a.id, timeout=5)
    assert s.node(a.id).state is NodeState.CANCELLED


def test_waiters_of_a_cancelled_node_get_node_error(s):
    """Review focus 4: waiters see NodeError, children block, retry heals the branch."""
    gate = block_lane(s)
    a = s.apply(call("n1", "head", n=2))
    b = s.apply(call(a.id, "tail", n=1))
    errors: list[str] = []

    def waiter():
        try:
            s.wait(a.id, timeout=5)
        except Exception as exc:  # noqa: BLE001 - recording what the waiter sees
            errors.append(type(exc).__name__)

    thread = threading.Thread(target=waiter)
    thread.start()
    s.cancel(a.id)
    gate.set()
    thread.join(5)
    assert errors == ["NodeError"]
    with pytest.raises(NodeError):
        s.wait(b.id, timeout=5)
    assert s.retry(a.id) == [a.id, b.id]
    pd.testing.assert_frame_equal(s.wait(b.id, timeout=5), VENTAS.head(2).tail(1))


def test_ready_nodes_cannot_be_cancelled(s):
    a = s.apply(call("n1", "head", n=1))
    s.wait(a.id)
    assert not s.cancel(a.id)
    assert s.retry(a.id) == []


def test_clear_failed_removes_errors_and_blocked_children(s):
    bad = s.apply(getitem("n1", "no_existe"))
    child = s.apply(call(bad.id, "head", n=1))
    ok = s.apply(call("n1", "head", n=1))
    with pytest.raises(NodeError):
        s.wait(child.id, timeout=5)
    s.wait(ok.id)
    out = s.clear_failed()
    assert out["ids"] == [bad.id, child.id]
    assert ok.id in s and bad.id not in s
    assert s.undo() and bad.id in s and child.id in s
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cancel.py -q`
Expected: FAIL (`AttributeError: 'Session' object has no attribute 'cancel'`)

- [ ] **Step 3: Implement** — `src/framelab/session/node.py`:

```python
class NodeState(StrEnum):
    PENDING = "pending"
    COMPUTING = "computing"
    READY = "ready"
    ERROR = "error"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FREED = "freed"  # result released from memory; recomputed when used (Task 8)
```

`Node` gains `cancel_requested: bool = False`; `info()` adds
`if self.cancel_requested and self.state in (NodeState.PENDING, NodeState.COMPUTING): out["cancelling"] = True`.
`NodeError.__init__`: when `node.error is None` and `node.state is NodeState.CANCELLED`, the detail is `"was cancelled"`.

`src/framelab/session/core.py`:

```python
from concurrent.futures import CancelledError

_DEAD = (NodeState.ERROR, NodeState.BLOCKED, NodeState.CANCELLED)

    def cancel(self, key: str) -> bool:
        """Stop a node: queued ones never run; running ones finish and are discarded."""
        with self._lock:
            node = self._nodes[self._resolve(key)]
            if node.state not in (NodeState.PENDING, NodeState.COMPUTING):
                return False
            future = self._futures.get(node.id)
            if node.state is NodeState.PENDING and future is not None and future.cancel():
                node.state = NodeState.CANCELLED
            else:
                node.cancel_requested = True
            self.rev += 1
            info = node.info()
        self._emit("node.state", info)
        return True

    def retry(self, key: str) -> list[str]:
        """Run again the node and its failed, blocked or cancelled descendants."""
        with self._lock:
            again = [d for d in self.descendants(key) if self._nodes[d].state in _DEAD]
            for d in again:
                node = self._nodes[d]
                node.state = NodeState.PENDING
                node.error, node.warnings, node.cancel_requested = None, (), False
                self._futures[d] = self._lane.submit(self._compute, d)
            if again:
                self.rev += 1
            infos = [self._nodes[d].info() for d in again]
        for info in infos:
            self._emit("node.state", info)
        return again

    def clear_failed(self) -> dict[str, Any]:
        """Delete every node in error, blocked or cancelled (one undo step)."""
        with self._lock:
            failed = [i for i, n in self._nodes.items() if not n.is_root and n.state in _DEAD]
        return self.delete(*failed) if failed else {"ids": [], "figures": []}
```

In `_compute`: at the start (inside the lock, after the dead-parents check) turn a pending `cancel_requested` into `CANCELLED` (emit, `raise NodeError(node)`); after `run_statement` returns, inside the lock, if `node.cancel_requested`: set `node.cancel_requested = False`, `node.state = NodeState.CANCELLED`, bump `rev`, emit and `raise NodeError(node)` without storing the result. In `wait()`, add `except CancelledError: raise NodeError(self._nodes[nid]) from None` (resolve `nid` before the `try`).

`src/framelab/protocol/schema.py`: `NodeStateName` gains `"cancelled"` and `"freed"`; `NodeInfo` gains `cancelling: NotRequired[bool]`. `src/framelab/transport/methods.py`:

```python
    dispatcher.register("node.cancel", lambda params, _b: {"cancelled": session.cancel(_id(params))})
    dispatcher.register("node.retry", lambda params, _b: {"ids": session.retry(_id(params))})
    dispatcher.register("graph.clear_failed", lambda params, _b: session.clear_failed())
```

Regenerate TS types.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_cancel.py tests/test_session_graph.py tests/test_history.py tests/test_tsgen.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/framelab tests/test_cancel.py frontend/src/generated/protocol.ts
git commit -m "Cancel queued or running nodes, retry failed branches, clear failed nodes"
```

---

### Task 6: Edit as new, replaying the branch

**Files:**
- Create: `tests/test_edit_as_new.py`
- Modify: `src/framelab/ops/op.py` (`remap_op`), `src/framelab/ops/__init__.py`, `src/framelab/session/core.py` (`edit_as_new`, `CannotEdit`), `src/framelab/transport/methods.py` (`node.edit_as_new`)

**Interfaces:**
- Consumes: `Session.batch()` (Task 4), `apply(..., force=...)`.
- Produces: `remap_op(op, mapping: Mapping[str, str]) -> Op`, `Session.edit_as_new(key, op, *, replay=True, name=None) -> dict[str, str]` (old id → new id), `CannotEdit` (code `cannot_edit`), protocol `node.edit_as_new {id, op, replay?, name?}` → `{"mapping"}`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/test_edit_as_new.py -->
```python
import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.ops import op_to_json, remap_op
from framelab.ops.build import call, col, gt, node, where
from framelab.session import Session
from framelab.session.core import CannotEdit

VENTAS = pd.DataFrame({"pais": ["AR", "UY", "AR", "BR"], "monto": [120.0, 50.0, 300.0, 45.0]})


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS.copy()), RootSpec("otros", VENTAS.head(1))])
    yield session
    session.close()


def test_remap_op_replaces_targets_and_references():
    op = call("n1", "merge", node("n2"), on="pais")
    data = op_to_json(remap_op(op, {"n1": "n5", "n2": "n6"}))
    assert data["target"] == "n5" and data["args"] == [{"t": "node", "id": "n6"}]


def test_edit_as_new_replays_the_branch(s):
    filt = s.apply(where("n1", gt(col("monto"), 100)))
    top = s.apply(call(filt.id, "head", n=2), name="top")
    total = s.apply(call(top.id, "sum", numeric_only=True))
    mapping = s.edit_as_new(filt.id, where("n1", gt(col("monto"), 48)))
    assert set(mapping) == {filt.id, top.id, total.id}
    new_top = s.node(mapping[top.id])
    assert new_top.name == "top_2" and not new_top.name_auto
    assert s.node(mapping[total.id]).parents == (new_top.id,)
    pd.testing.assert_frame_equal(s.wait(new_top.id), VENTAS[VENTAS["monto"] > 48].head(2))
    pd.testing.assert_frame_equal(s.wait(top.id), VENTAS[VENTAS["monto"] > 100].head(2))


def test_edit_without_replay_makes_only_the_sibling(s):
    filt = s.apply(where("n1", gt(col("monto"), 100)))
    s.apply(call(filt.id, "head", n=2))
    mapping = s.edit_as_new(filt.id, where("n1", gt(col("monto"), 10)), replay=False)
    assert list(mapping) == [filt.id]
    assert len(s) == 5


def test_one_undo_removes_the_whole_new_branch(s):
    filt = s.apply(where("n1", gt(col("monto"), 100)))
    s.apply(call(filt.id, "head", n=2))
    before = [n.id for n in s.nodes()]
    mapping = s.edit_as_new(filt.id, where("n1", gt(col("monto"), 10)))
    assert s.undo()
    assert [n.id for n in s.nodes()] == before
    assert s.redo() and all(new in s for new in mapping.values())


def test_roots_cannot_be_edited(s):
    with pytest.raises(CannotEdit):
        s.edit_as_new("n1", call("n2", "head", n=1))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_edit_as_new.py -q`
Expected: FAIL with `ImportError: cannot import name 'remap_op'`

- [ ] **Step 3: Implement** — in `src/framelab/ops/op.py` (and export it from `ops/__init__.py`):

```python
def remap_op(op: Op, mapping: Mapping[str, str]) -> Op:
    """The same op reading other nodes: every node id found in ``mapping`` is replaced."""

    def fix(obj: Any) -> Any:
        if isinstance(obj, dict):
            if obj.get("t") == "node" and obj.get("id") in mapping:
                return {**obj, "id": mapping[obj["id"]]}
            return {k: fix(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [fix(v) for v in obj]
        return obj

    data = fix(op_to_json(op))
    if data.get("target") in mapping:
        data["target"] = mapping[data["target"]]
    return op_from_json(data)
```

In `src/framelab/session/core.py`:

```python
from ..ops import Op, remap_op


class CannotEdit(FramelabError, ValueError):
    code = "cannot_edit"

    def edit_as_new(
        self, key: str, op: Op, *, replay: bool = True, name: str | None = None
    ) -> dict[str, str]:
        """A sibling of ``key`` built from ``op``; with ``replay`` its descendants are rebuilt
        on the sibling. The original branch stays as it was. Returns old id -> new id."""
        original = self.node(key)
        if original.is_root:
            raise CannotEdit(f"{original.name} is data passed to fl.explore()")
        mapping: dict[str, str] = {}
        with self.batch():
            mapping[original.id] = self.apply(op, name=name).id
            if replay:
                for d in self.descendants(original.id)[1:]:
                    child = self.node(d)
                    taken = set(self.names) | self.plots.names()
                    wanted = None if child.name_auto else unique_name(child.name, taken)
                    new_op = remap_op(child.op, mapping)  # type: ignore[arg-type]
                    mapping[d] = self.apply(new_op, name=wanted, force=child.force).id
        return mapping
```

In `src/framelab/transport/methods.py`:

```python
    def edit_as_new(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        mapping = session.edit_as_new(
            _id(params),
            op_from_json(params.get("op")),
            replay=params.get("replay", True) is not False,
            name=params.get("name"),
        )
        return {"mapping": mapping}

    dispatcher.register("node.edit_as_new", edit_as_new)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_edit_as_new.py tests/test_ops.py tests/test_history.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/framelab tests/test_edit_as_new.py
git commit -m "Edit as new: a sibling node with its branch replayed, one undo step"
```

---

### Task 7: Guards — estimated sizes and string aggregations

**Files:**
- Create: `src/framelab/engine/guards.py`, `tests/test_guards.py`
- Modify: `src/framelab/options.py` (`performance.guard_ram_fraction`, `performance.cache_fraction`), `src/framelab/session/core.py` (`__init__` keyword `guard_bytes`, `_guard_limit`, `_ready_values`, guards in `apply`/`preview`/`_compute`), `src/framelab/session/document.py` (force flag), `src/framelab/transport/methods.py` (`force` in `node.apply`)

**Interfaces:**
- Produces: `GuardError(message, *, kind="size", rows=None, nbytes=None)` with `code` `"too_big"` or `"string_aggregation"`, `Estimate(rows, columns).nbytes`, `estimate(op, values) -> Estimate | None`, `check(op, values, *, limit_bytes)`, `NUMERIC_AGGS`, `Session(roots, options=None, *, guard_bytes=None, cache_bytes=None)` (`cache_bytes` used in Task 8), `Session.apply(..., force=False)`, document entries with `"force": true`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/test_guards.py -->
```python
import threading

import numpy as np
import pandas as pd
import pytest

from framelab.engine.guards import GuardError, estimate
from framelab.naming import RootSpec
from framelab.ops.build import call, func, getitem, node, ref_col
from framelab.session import NodeError, Session

LEFT = pd.DataFrame({"k": [1, 1, 2, 3, np.nan], "a": range(5)})
RIGHT = pd.DataFrame({"k": [1, 1, 1, 2, 4, np.nan], "b": range(6)})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"on": "k", "how": "inner"},
        {"on": "k", "how": "left"},
        {"on": "k", "how": "right"},
        {"on": "k", "how": "outer"},
        {"how": "cross"},
        {"how": "inner"},  # default keys: the shared columns
    ],
)
def test_merge_estimates_are_exact(kwargs):
    est = estimate(call("n1", "merge", node("n2"), **kwargs), {"n1": LEFT, "n2": RIGHT})
    assert est is not None and est.rows == len(LEFT.merge(RIGHT, **kwargs))


def test_left_on_right_on_and_function_merge():
    right = RIGHT.rename(columns={"k": "kk"})
    op = call("n1", "merge", node("n2"), left_on="k", right_on="kk", how="left")
    assert estimate(op, {"n1": LEFT, "n2": right}).rows == len(LEFT.merge(right, left_on="k", right_on="kk", how="left"))
    op = func("merge", node("n1"), node("n2"), on="k")
    assert estimate(op, {"n1": LEFT, "n2": RIGHT}).rows == len(pd.merge(LEFT, RIGHT, on="k"))


def test_reshaping_estimates():
    frame = pd.DataFrame({"g": ["a", "b", "a"], "h": ["x", "y", "y"], "v": [1, 2, 3], "l": [[1, 2], [], [3]]})
    dummies = estimate(func("get_dummies", node("n1"), columns=["g", "h"]), {"n1": frame})
    assert (dummies.rows, dummies.columns) == pd.get_dummies(frame, columns=["g", "h"]).shape
    exploded = estimate(call("n1", "explode", "l"), {"n1": frame})
    assert exploded.rows == len(frame.explode("l"))
    pivot = estimate(call("n1", "pivot_table", index=ref_col("g"), columns=ref_col("h"), values=ref_col("v")), {"n1": frame})
    assert (pivot.rows, pivot.columns) == frame.pivot_table(index="g", columns="h", values="v").shape


def test_big_merge_is_refused_before_creating_a_node():
    s = Session([RootSpec("left", LEFT), RootSpec("right", RIGHT)], guard_bytes=100)
    try:
        with pytest.raises(GuardError) as info:
            s.apply(call("n1", "merge", node("n2"), on="k"))
        assert info.value.code == "too_big" and info.value.rows == 8 and len(s) == 2
        with pytest.raises(GuardError):
            s.preview(call("n1", "merge", node("n2"), on="k"))
        merged = s.apply(call("n1", "merge", node("n2"), on="k"), force=True)
        assert len(s.wait(merged.id)) == 8 and s.node(merged.id).force
    finally:
        s.close()


def test_guard_runs_when_parents_were_not_ready():
    s = Session([RootSpec("left", LEFT), RootSpec("right", RIGHT)], guard_bytes=100)
    try:
        gate = threading.Event()
        s._lane.submit(gate.wait, 10)
        head = s.apply(call("n1", "head", n=5))
        merged = s.apply(call(head.id, "merge", node("n2"), on="k"))
        gate.set()
        with pytest.raises(NodeError, match="GuardError"):
            s.wait(merged.id, timeout=5)
    finally:
        s.close()


def test_string_aggregation_guard():
    frame = pd.DataFrame({"pais": ["AR", "AR", "UY"], "nombre": ["a", "b", "c"], "monto": [1.0, 2.0, 3.0]})
    s = Session([RootSpec("ventas", frame)])
    try:
        grouped = s.apply(call("n1", "groupby", by=ref_col("pais")))
        s.wait(grouped.id)  # guards run before creating a node once the parents are ready
        with pytest.raises(GuardError) as info:
            s.apply(call(grouped.id, "sum"))
        assert info.value.code == "string_aggregation" and "nombre" in str(info.value)
        ok = s.apply(call(grouped.id, "sum", numeric_only=True))
        assert list(s.wait(ok.id).columns) == ["monto"]
        chosen = s.apply(getitem(grouped.id, ["monto"]))
        s.wait(s.apply(call(chosen.id, "sum")).id)
        forced = s.apply(call(grouped.id, "sum"), force=True)
        assert s.wait(forced.id).loc["AR", "nombre"] == "ab"
    finally:
        s.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_guards.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'framelab.engine.guards'`

- [ ] **Step 3: Implement the guards**

<!-- file: src/framelab/engine/guards.py -->
```python
"""Guards: refuse operations whose result would not fit in memory, before running them.

Merge row counts are exact (key counts on both sides, spec: "estimación exacta O(n)");
reshaping estimates are exact or slightly high. ``force=True`` skips every guard.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..codegen.literals import label_text
from ..errors import FramelabError
from ..ops import Op
from ..ops.values import Col, ListV, Lit, NodeRef

__all__ = ["NUMERIC_AGGS", "Estimate", "GuardError", "check", "estimate"]

NUMERIC_AGGS = frozenset({"sum", "mean", "median", "std", "var", "sem", "prod", "skew", "quantile"})
BYTES_PER_CELL = 8


class GuardError(FramelabError, ValueError):
    code = "too_big"

    def __init__(
        self, message: str, *, kind: str = "size", rows: int | None = None, nbytes: int | None = None
    ) -> None:
        super().__init__(message)
        self.kind, self.rows, self.nbytes = kind, rows, nbytes
        if kind == "string_aggregation":
            self.code = "string_aggregation"


@dataclass(frozen=True)
class Estimate:
    rows: int
    columns: int

    @property
    def nbytes(self) -> int:
        return self.rows * max(self.columns, 1) * BYTES_PER_CELL


def _plain(v: Any, values: Mapping[str, Any]) -> Any:
    if isinstance(v, Lit):
        return v.value
    if isinstance(v, Col):
        return v.label
    if isinstance(v, NodeRef):
        return values.get(v.id)
    if isinstance(v, ListV):
        return [_plain(i, values) for i in v.items]
    return None


def _labels(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _merge(left: Any, right: Any, kw: Mapping[str, Any]) -> Estimate | None:
    if isinstance(right, pd.Series):
        right = right.to_frame()
    if not isinstance(left, pd.DataFrame) or not isinstance(right, pd.DataFrame):
        return None
    how = kw.get("how") or "inner"
    if how == "cross":
        return Estimate(len(left) * len(right), left.shape[1] + right.shape[1])
    if kw.get("left_index") or kw.get("right_index"):
        return None
    on = _labels(kw.get("on"))
    lk = _labels(kw.get("left_on")) or on
    rk = _labels(kw.get("right_on")) or on
    if not lk and not rk:
        lk = rk = [c for c in left.columns if c in set(right.columns)]
    if not lk or len(lk) != len(rk):
        return None
    try:
        lc = left.groupby(lk, dropna=False, observed=True).size()
        rc = right.groupby(rk, dropna=False, observed=True).size()
    except (KeyError, TypeError, ValueError):
        return None
    rc.index = rc.index.set_names(lc.index.names)
    both = pd.concat([lc.rename("l"), rc.rename("r")], axis=1).fillna(0)
    inner = int((both["l"] * both["r"]).sum())
    left_only = int(both.loc[both["r"] == 0, "l"].sum())
    right_only = int(both.loc[both["l"] == 0, "r"].sum())
    rows = {
        "inner": inner,
        "left": inner + left_only,
        "right": inner + right_only,
        "outer": inner + left_only + right_only,
    }.get(how)
    if rows is None:
        return None
    shared = len(lk) if not kw.get("left_on") and not kw.get("right_on") else 0
    return Estimate(rows, left.shape[1] + right.shape[1] - shared)


def _encoded(frame: pd.DataFrame) -> list[Any]:
    return [
        c
        for c, dtype in frame.dtypes.items()
        if pd.api.types.is_object_dtype(dtype)
        or pd.api.types.is_string_dtype(dtype)
        or isinstance(dtype, pd.CategoricalDtype)
    ]


def _get_dummies(data: Any, kw: Mapping[str, Any]) -> Estimate | None:
    dropna = not kw.get("dummy_na", False)
    if isinstance(data, pd.Series):
        return Estimate(len(data), int(data.nunique(dropna=dropna)))
    if not isinstance(data, pd.DataFrame):
        return None
    columns = [c for c in _labels(kw.get("columns")) or _encoded(data) if c in data.columns]
    extra = sum(int(data[c].nunique(dropna=dropna)) for c in columns)
    return Estimate(len(data), data.shape[1] - len(columns) + extra)


def _explode(obj: Any, column: Any) -> Estimate | None:
    if isinstance(obj, pd.Series):
        series, width = obj, 1
    elif isinstance(obj, pd.DataFrame) and column is not None:
        first = _labels(column)[0]
        if first not in obj.columns:
            return None
        series, width = obj[first], obj.shape[1]
    else:
        return None

    def length(x: Any) -> int:
        if pd.api.types.is_list_like(x) and not isinstance(x, (str, bytes)):
            return max(len(x), 1)
        return 1

    return Estimate(int(series.map(length).sum()), width)


def _pivot(frame: Any, kw: Mapping[str, Any]) -> Estimate | None:
    if not isinstance(frame, pd.DataFrame):
        return None
    index, columns = _labels(kw.get("index")), _labels(kw.get("columns"))
    if not index and not columns:
        return None
    try:
        rows = len(frame[index].drop_duplicates()) if index else 1
        cols = len(frame[columns].drop_duplicates()) if columns else 1
    except KeyError:
        return None
    grouping = set(index) | set(columns)
    values = _labels(kw.get("values")) or [c for c in frame.columns if c not in grouping]
    return Estimate(rows, cols * max(len(values), 1))


def _crosstab(index: Any, columns: Any) -> Estimate | None:
    if not isinstance(index, pd.Series) or not isinstance(columns, pd.Series):
        return None
    return Estimate(int(index.nunique()), int(columns.nunique()))


def estimate(op: Op, values: Mapping[str, Any]) -> Estimate | None:
    """The size of ``op``'s result, when framelab knows how to predict it cheaply."""
    kw = {k: _plain(v, values) for k, v in op.kwargs}
    args = [_plain(a, values) for a in op.args]
    target = values.get(op.target) if op.target else None
    first = args[0] if args else None
    if op.kind == "call" and not op.accessor:
        if op.name == "merge":
            return _merge(target, first if args else kw.get("right"), kw)
        if op.name == "explode":
            return _explode(target, first if args else kw.get("column"))
        if op.name == "pivot_table":
            return _pivot(target, kw)
    if op.kind == "func":
        second = args[1] if len(args) > 1 else None
        if op.name == "merge":
            left = first if first is not None else kw.get("left")
            return _merge(left, second if second is not None else kw.get("right"), kw)
        if op.name == "get_dummies":
            return _get_dummies(first if args else kw.get("data"), kw)
        if op.name == "pivot_table":
            return _pivot(first if args else kw.get("data"), kw)
        if op.name == "crosstab":
            columns = second if second is not None else kw.get("columns")
            return _crosstab(first if args else kw.get("index"), columns)
    return None


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _string_aggregation(op: Op, values: Mapping[str, Any]) -> None:
    if op.kind != "call" or op.accessor or op.name not in NUMERIC_AGGS:
        return
    if any(k == "numeric_only" for k, _ in op.kwargs):
        return
    from pandas.api.typing import DataFrameGroupBy

    grouped = values.get(op.target) if op.target else None
    if not isinstance(grouped, DataFrameGroupBy):
        return
    try:
        frame = grouped._obj_with_exclusions  # the columns the aggregation touches (private API)
    except AttributeError:
        return
    text = [
        c
        for c, dtype in frame.dtypes.items()
        if not (
            pd.api.types.is_numeric_dtype(dtype)
            or pd.api.types.is_bool_dtype(dtype)
            or pd.api.types.is_datetime64_any_dtype(dtype)
            or pd.api.types.is_timedelta64_dtype(dtype)
        )
    ]
    if text:
        shown = ", ".join(label_text(c) for c in text[:5])
        raise GuardError(
            f"{op.name}() would also try to combine the text columns {shown}. Add "
            "numeric_only=True or choose the columns first (or run it anyway to combine them).",
            kind="string_aggregation",
        )


def check(op: Op, values: Mapping[str, Any], *, limit_bytes: int) -> None:
    """Raise GuardError when ``op`` should not run as it is."""
    _string_aggregation(op, values)
    est = estimate(op, values)
    if est is not None and est.nbytes > limit_bytes:
        raise GuardError(
            f"the result would have about {est.rows:,} rows × {est.columns} columns "
            f"(~{_human(est.nbytes)}), more than the {_human(limit_bytes)} framelab allows. "
            "Check the keys or filter first, or run it anyway.",
            rows=est.rows,
            nbytes=est.nbytes,
        )
```

- [ ] **Step 4: Wire the guards into the session** — `src/framelab/options.py`: add to `DEFAULT_OPTIONS`

```python
    Option("performance.guard_ram_fraction", 0.5, float),
    Option("performance.cache_fraction", 0.25, float),
```

`src/framelab/session/core.py`:

```python
import psutil

from ..engine import guards

    def __init__(
        self,
        roots: list[RootSpec],
        options: OptionsRegistry | None = None,
        *,
        guard_bytes: int | None = None,
        cache_bytes: int | None = None,
    ) -> None:
        ...
        self._guard_bytes = guard_bytes
        self._cache_bytes = cache_bytes  # Task 8

    def _guard_limit(self) -> int:
        if self._guard_bytes is not None:
            return self._guard_bytes
        fraction = self._options.get("performance.guard_ram_fraction")
        return int(psutil.virtual_memory().available * fraction)

    def _ready_values(self, ids: tuple[str, ...]) -> dict[str, Any] | None:
        """Parent values when every parent is ready (guards run before the node exists)."""
        with self._lock:
            out = {}
            for nid in ids:
                if self._nodes[nid].state is not NodeState.READY or nid not in self._results:
                    return None
                out[nid] = self._results[nid]
            return out
```

- `apply(self, op, *, name=None, node_id=None, force=False)`: after `op.validate()` and the unknown-parent check (move that check before the guard), when `not force and not self._replaying`: `values = self._ready_values(op.parents())`; if not `None`, `guards.check(op, values, limit_bytes=self._guard_limit())` (outside the lock). Store `force` on the node.
- `preview(op, name=None)`: after validation, the same `_ready_values` + `guards.check` (raises `GuardError`).
- `_compute`: inside the existing `try`, before `run_statement`, when `not node.force`: `guards.check(node.op, {p: self._results[p] for p in node.parents}, limit_bytes=self._guard_limit())` (Task 8 replaces `self._results[p]` with `self._value(p)`), so a guard failure becomes an `error` node whose `ErrorDetail.type` is `"GuardError"`.

`src/framelab/session/document.py`: entries for non-root nodes add `"force": True` when `node.force`; `from_document` passes `force=entry.get("force", False)` to `apply`.

`src/framelab/transport/methods.py` `apply`: `session.apply(op_from_json(params.get("op")), name=params.get("name"), force=params.get("force") is True)`.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_guards.py tests/test_session_graph.py tests/test_methods.py tests/test_document.py tests/test_options.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/framelab tests/test_guards.py
git commit -m "Guards: exact merge sizes, reshaping estimates and string aggregations, with force"
```

---

### Task 8: Result cache — memory budget, freed nodes, pins

**Files:**
- Create: `src/framelab/engine/cache.py`, `tests/test_cache.py`
- Modify: `src/framelab/session/core.py` (`_store`, `_evict`, `_value`, `_rematerialize`, `wait`, `_compute`, `set_pins`, `delete`), `src/framelab/transport/methods.py` (`session.pins`)

**Interfaces:**
- Consumes: `Session(..., cache_bytes=None)` and `performance.cache_fraction` (Task 7), `NodeState.FREED` (Task 5).
- Produces: `buffers(value) -> list[tuple[int, int]]`, `value_bytes(value, exclude=frozenset()) -> int`, `default_budget(fraction) -> int`, `ResultCache(budget)` with `add(nid, nbytes)`, `touch(nid)`, `discard(nid)`, `pinned: set[str]`, `total`, `victims() -> list[str]`; `Session.set_pins(ids)`; protocol `session.pins {ids}` → `{"pinned": [...]}`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/test_cache.py -->
```python
import threading
import time

import numpy as np
import pandas as pd
import pytest

from framelab.engine.cache import ResultCache, buffers, value_bytes
from framelab.naming import RootSpec
from framelab.ops.build import call, col, mul, setcol
from framelab.session import NodeState, Session

FRAME = pd.DataFrame({"a": np.arange(1000.0), "s": [f"x{i}" for i in range(1000)]})


def wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_views_of_the_roots_cost_nothing():
    roots = {address for address, _ in buffers(FRAME)}
    assert value_bytes(FRAME["a"], roots) == 0
    assert value_bytes(FRAME.iloc[:10], roots) == 0
    assert 0 < value_bytes(FRAME.head(10), roots) <= 80  # pandas 3 head() copies numeric columns
    assert value_bytes(FRAME["a"] * 2, roots) >= 8000


def test_victims_are_least_recently_used_and_never_pinned():
    cache = ResultCache(budget=100)
    for nid in ("n2", "n3", "n4"):
        cache.add(nid, 60)
    cache.touch("n2")
    cache.pinned = {"n3"}
    assert cache.victims() == ["n4", "n2"]


@pytest.fixture
def tiny_cache():
    s = Session([RootSpec("v", FRAME.copy())], cache_bytes=1)
    yield s
    s.close()


def test_evicted_nodes_are_recomputed_when_used(tiny_cache):
    s = tiny_cache
    doubled = s.apply(setcol("n1", "b", mul(col("a"), 2)))
    expected = FRAME.assign(b=FRAME["a"] * 2)
    pd.testing.assert_frame_equal(s.wait(doubled.id), expected)
    assert wait_for(lambda: s.node(doubled.id).state is NodeState.FREED)
    pd.testing.assert_frame_equal(s.wait(doubled.id, timeout=5), expected)
    assert s.node("n1").state is NodeState.READY  # roots are never freed


def test_pinned_nodes_stay(tiny_cache):
    s = tiny_cache
    gate = threading.Event()
    s._lane.submit(gate.wait, 10)
    doubled = s.apply(setcol("n1", "b", mul(col("a"), 2)))
    s.set_pins([doubled.id])
    gate.set()
    s.wait(doubled.id, timeout=5)
    time.sleep(0.05)
    assert s.node(doubled.id).state is NodeState.READY


def test_evicted_parent_is_recomputed_for_a_queued_child(tiny_cache):
    """Review focus 2: children and table windows recompute freed parents transparently."""
    s = tiny_cache
    doubled = s.apply(setcol("n1", "b", mul(col("a"), 2)))
    s.wait(doubled.id)
    assert wait_for(lambda: s.node(doubled.id).state is NodeState.FREED)
    total = s.apply(call(doubled.id, "sum", numeric_only=True))
    assert s.wait(total.id, timeout=5)["b"] == FRAME["a"].sum() * 2
    data, meta = s.window(doubled.id, offset=0, limit=5)
    assert meta["nrows_total"] == 1000 and data


def test_figures_draw_freed_sources(tiny_cache):
    s = tiny_cache
    doubled = s.apply(setcol("n1", "b", mul(col("a"), 2)))
    s.wait(doubled.id)
    assert wait_for(lambda: s.node(doubled.id).state is NodeState.FREED)
    fig = s.plots.create(doubled.id)
    spec = fig["spec"]
    spec["axes"][0]["layers"] = [{"kind": "line", "source": doubled.id, "y": [{"col": "b"}]}]
    s.plots.update(fig["id"], spec)
    png, meta = s.plots.render(fig["id"], width_px=200, height_px=150)
    assert png.startswith(b"\x89PNG") and meta["errors"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cache.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'framelab.engine.cache'`

- [ ] **Step 3: Implement the accounting**

<!-- file: src/framelab/engine/cache.py -->
```python
"""Memory accounting for node results: bytes per node, least-recently-used eviction, pins.

Buffers that belong to the roots are not counted: views of the user's data cost nothing extra
(Copy-on-Write). Everything else is counted per node, which over-counts views shared between
nodes and so errs on the side of freeing memory early.
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from typing import Any

import numpy as np
import pandas as pd
import psutil

__all__ = ["ResultCache", "buffers", "default_budget", "value_bytes"]


def _base(arr: np.ndarray) -> np.ndarray:
    while isinstance(arr.base, np.ndarray):
        arr = arr.base
    return arr


def _array_buffers(arr: Any) -> list[tuple[int, int]]:
    if isinstance(arr, np.ndarray):
        base = _base(arr)
        return [(base.__array_interface__["data"][0], int(base.nbytes))]
    if isinstance(arr, pd.arrays.ArrowExtensionArray):
        import pyarrow as pa

        data = arr.__arrow_array__()
        chunks = data.chunks if isinstance(data, pa.ChunkedArray) else [data]
        return [(b.address, b.size) for c in chunks for b in c.buffers() if b is not None]
    for attr in ("asi8", "codes"):  # datetime/timedelta/period arrays, categoricals
        inner = getattr(arr, attr, None)
        if isinstance(inner, np.ndarray):
            return _array_buffers(inner)
    return [(id(arr), int(getattr(arr, "nbytes", 0) or 0))]


def _column_buffers(s: pd.Series) -> list[tuple[int, int]]:
    if isinstance(s.dtype, np.dtype):
        return _array_buffers(s.to_numpy(copy=False))
    return _array_buffers(s.array)


def _index_buffers(index: pd.Index) -> list[tuple[int, int]]:
    if isinstance(index, pd.RangeIndex):
        return []
    if isinstance(index, pd.MultiIndex):
        return [(id(index), int(index.memory_usage()))]
    if isinstance(index.dtype, np.dtype):
        return _array_buffers(index.to_numpy(copy=False))
    return _array_buffers(index.array)


def buffers(value: Any) -> list[tuple[int, int]]:
    """(address, size) of the memory behind a value; views share their base's address."""
    try:
        if isinstance(value, pd.DataFrame):
            out: list[tuple[int, int]] = []
            for j in range(value.shape[1]):
                out += _column_buffers(value.iloc[:, j])
            return out + _index_buffers(value.index)
        if isinstance(value, pd.Series):
            return _column_buffers(value) + _index_buffers(value.index)
        if isinstance(value, pd.Index):
            return _index_buffers(value)
        if isinstance(value, np.ndarray):
            return _array_buffers(value)
    except Exception:  # an exotic dtype: fall back to pandas' own estimate
        usage = getattr(value, "memory_usage", None)
        total = usage(deep=False) if callable(usage) else 0
        return [(id(value), int(getattr(total, "sum", lambda: total)()))]
    return [(id(value), sys.getsizeof(value))]  # scalars; groupby objects reference their parent


def value_bytes(value: Any, exclude: set[int] | frozenset[int] = frozenset()) -> int:
    seen: set[int] = set()
    total = 0
    for address, size in buffers(value):
        if address in exclude or address in seen:
            continue
        seen.add(address)
        total += size
    return total


def default_budget(fraction: float) -> int:
    return int(psutil.virtual_memory().total * fraction)


class ResultCache:
    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.pinned: set[str] = set()
        self._sizes: OrderedDict[str, int] = OrderedDict()

    @property
    def total(self) -> int:
        return sum(self._sizes.values())

    def add(self, nid: str, nbytes: int) -> None:
        self._sizes[nid] = nbytes
        self._sizes.move_to_end(nid)

    def touch(self, nid: str) -> None:
        if nid in self._sizes:
            self._sizes.move_to_end(nid)

    def discard(self, nid: str) -> None:
        self._sizes.pop(nid, None)

    def victims(self) -> list[str]:
        """Least recently used unpinned results to free until the total fits the budget."""
        over = self.total - self.budget
        out = []
        for nid, size in self._sizes.items():
            if over <= 0:
                break
            if nid not in self.pinned:
                out.append(nid)
                over -= size
        return out
```

- [ ] **Step 4: Wire it into the session** — `src/framelab/session/core.py`:

```python
from ..engine.cache import ResultCache, buffers, default_budget, value_bytes

# in __init__, after options/guard settings
        budget = cache_bytes if cache_bytes is not None else default_budget(
            self._options.get("performance.cache_fraction")
        )
        self._cache = ResultCache(budget)
        self._root_buffers: set[int] = set()
# for every root, after freezing it
            self._root_buffers.update(address for address, _ in buffers(frozen))

    # ---- memory ----------------------------------------------------------------------------
    def _store(self, nid: str, value: Any) -> list[str]:
        """Keep a result (lock held); returns the nodes to free to stay within budget."""
        self._results[nid] = value
        self._cache.add(nid, value_bytes(value, self._root_buffers))
        return self._cache.victims()

    def _evict(self, ids: list[str]) -> None:
        infos = []
        with self._lock:
            for nid in ids:
                node = self._nodes.get(nid)
                if node is None or node.state is not NodeState.READY or node.is_root:
                    continue
                self._results.pop(nid, None)
                self._encoders.pop(nid, None)
                self._futures.pop(nid, None)  # a finished future would keep the value alive
                self._cache.discard(nid)
                node.state = NodeState.FREED
                infos.append(node.info())
            if infos:
                self.rev += 1
        for info in infos:
            self._emit("node.state", info)

    def _value(self, nid: str) -> Any:
        """A node's value on the compute lane, recomputing freed ancestors first."""
        with self._lock:
            if nid in self._results:
                self._cache.touch(nid)
                return self._results[nid]
            node = self._nodes[nid]
            parents = node.parents
        values = {p: self._value(p) for p in parents}
        with self._lock:
            names = self.variable_names()
            rendered = render_op(node.op, node.name, names)  # type: ignore[arg-type]
        value, _ = run_statement(rendered.executed, node.name, {names[p]: v for p, v in values.items()})
        with self._lock:
            victims = self._store(nid, value)
            node.state = NodeState.READY
            self.rev += 1
            info = node.info()
        self._emit("node.state", info)
        self._evict([v for v in victims if v != nid])
        return value

    def _rematerialize(self, nid: str) -> Any:
        return self._value(nid)

    def set_pins(self, ids: list[str]) -> list[str]:
        """Nodes the UI shows (open tabs, figure sources): never freed while pinned."""
        with self._lock:
            self._cache.pinned = {i for i in ids if i in self._nodes}
            victims = self._cache.victims()
            pinned = sorted(self._cache.pinned)
        self._evict(victims)
        return pinned
```

- `wait()`: resolve `nid`; if the node is `FREED`, set it `PENDING`, submit `self._rematerialize` to the lane, keep that future in `self._futures[nid]`, bump `rev` and emit its state; then `self._cache.touch(nid)` and wait on the future as before.
- `_compute()`: take the parent values with `self._value(p)` (outside the lock) instead of reading `self._results[p]`; pass the same values to `guards.check`. After success, `victims = self._store(nid, value)` under the lock, and `self._evict(victims)` after emitting the ready state.
- `delete()`: also `self._cache.discard(i)` for every removed node.

In `src/framelab/transport/methods.py`:

```python
    def pins(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        ids = params.get("ids", [])
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise BadRequest("ids must be a list of node ids")
        return {"pinned": session.set_pins(ids)}

    dispatcher.register("session.pins", pins)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_cache.py tests/test_session_graph.py tests/test_cancel.py tests/test_guards.py tests/test_table.py tests/test_plot.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/framelab tests/test_cache.py
git commit -m "Result cache: memory budget, least-recently-used freeing, pins, recompute on demand"
```

---

### Task 9: The generated pandas catalog

**Files:**
- Create: `tools/gen_catalog.py`, `src/framelab/catalog/__init__.py`, `src/framelab/catalog/pandas.json.gz` (generated), `tests/test_catalog.py`
- Modify: `.gitignore` (`tools/.cache/`), `src/framelab/transport/methods.py` (`catalog.members`)

**Interfaces:**
- Produces: `load() -> Catalog` (cached), `Catalog.pandas_version`, `Catalog.owners`, `Catalog.member(owner, name) -> Member | None`, `Catalog.members(owner) -> list[Member]`, `Member(owner, name, kind, category, summary, params, returns, mutates, preview, allowed, generated)` with `describe()`, `Param(name, widget, required, default, choices, annotation, variadic)`, `owner_types() -> dict[str, type]`; protocol `catalog.members {owner}` → `{"pandas_version", "members": [...]}`. Owners: `DataFrame, Series, DataFrameGroupBy, SeriesGroupBy, Resampler, Rolling, Expanding, ExponentialMovingWindow, Index, str, dt, cat, pd`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/test_catalog.py -->
```python
import pandas as pd
import pytest

from framelab.catalog import load, owner_types

OWNERS = {
    "DataFrame", "Series", "DataFrameGroupBy", "SeriesGroupBy", "Resampler", "Rolling",
    "Expanding", "ExponentialMovingWindow", "Index", "str", "dt", "cat", "pd",
}  # fmt: skip


@pytest.fixture(scope="module")
def catalog():
    return load()


def test_every_owner_is_there(catalog):
    assert set(catalog.owners) == OWNERS
    assert catalog.pandas_version.startswith("3.")


def test_head(catalog):
    head = catalog.member("DataFrame", "head")
    assert head.category == "Indexing, iteration"
    assert head.summary.startswith("Return the first")
    [n] = head.params
    assert (n.name, n.widget, n.required, n.default) == ("n", "int", False, 5)
    assert (head.returns, head.mutates, head.preview, head.allowed) == ("DataFrame", False, "rowwise", True)


def test_parameters(catalog):
    params = {p.name: p for p in catalog.member("DataFrame", "sort_values").params}
    assert params["by"].widget == "columns" and params["by"].required
    assert params["ascending"].widget == "bool" and params["ascending"].default is True
    keep = {p.name: p for p in catalog.member("DataFrame", "drop_duplicates").params}["keep"]
    assert keep.widget == "choice" and "first" in keep.choices


def test_return_kinds_and_mutation(catalog):
    assert catalog.member("DataFrame", "groupby").returns == "GroupBy"
    assert catalog.member("Series", "rolling").returns == "Window"
    assert catalog.member("DataFrame", "shape").returns == "Value"
    assert catalog.member("str", "upper").returns == "Series"
    assert catalog.member("dt", "year").returns == "Series"
    for name in ("insert", "pop", "update"):
        assert catalog.member("DataFrame", name).mutates, name
    assert not catalog.member("DataFrame", "sort_values").mutates


def test_policy_and_categories(catalog):
    assert not catalog.member("DataFrame", "to_csv").allowed
    assert not catalog.member("DataFrame", "plot").allowed
    assert catalog.member("str", "upper").category == "String handling"
    assert catalog.member("pd", "concat").category == "Data manipulations"
    assert catalog.member("DataFrame", "describe").preview == "sampled_stat"


def test_generated_members_exist_at_runtime(catalog):
    for owner, cls in owner_types().items():
        names = [m.name for m in catalog.members(owner) if m.generated]
        missing = [n for n in names if not hasattr(cls, n)]
        assert len(missing) <= 0.03 * len(names), (owner, missing)


def test_members_missing_from_the_file_appear_under_other(catalog, monkeypatch):
    known = dict(catalog._members["DataFrame"])
    known.pop("head")
    monkeypatch.setitem(catalog._members, "DataFrame", known)
    head = catalog.member("DataFrame", "head")
    assert head.category == "Other" and not head.generated
    assert "head" in [m.name for m in catalog.members("DataFrame")]


def test_the_file_is_small():
    from importlib import resources

    size = len(resources.files("framelab.catalog").joinpath("pandas.json.gz").read_bytes())
    assert size < 400_000


def test_catalog_method():
    from framelab.naming import RootSpec
    from framelab.session import Session
    from framelab.transport.dispatcher import Dispatcher

    s = Session([RootSpec("v", pd.DataFrame({"a": [1]}))])
    try:
        env, _ = Dispatcher(s).handle(
            {"v": 1, "id": "1", "type": "req", "method": "catalog.members", "params": {"owner": "Series"}},
            [],
        )
        names = [m["name"] for m in env["result"]["members"]]
        assert "value_counts" in names and env["result"]["pandas_version"].startswith("3.")
    finally:
        s.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_catalog.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'framelab.catalog'`

- [ ] **Step 3: Write the generator**

<!-- file: tools/gen_catalog.py -->
```python
"""Generate ``src/framelab/catalog/pandas.json.gz`` from the installed pandas.

Run it by hand when the supported pandas version changes (network access the first time):

    .venv/bin/python tools/gen_catalog.py

- categories: pandas' API reference (``doc/source/reference/*.rst`` at the installed version's
  git tag), downloaded once into ``tools/.cache/``;
- parameters: ``inspect.signature`` plus numpydoc type lines (``{'a', 'b'}`` choices);
- return kinds and mutation: probes on a tiny frame (never IO, plotting or string evaluation).
The output is deterministic (sorted keys, gzip mtime 0). Deprecated members are left out.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import gzip
import inspect
import io
import json
import re
import sys
import types
import urllib.request
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from framelab.ops.policy import ALLOWED_PD_FUNCS, method_allowed  # noqa: E402
from framelab.ops.values import OpError, encode_scalar  # noqa: E402

OUT = ROOT / "src" / "framelab" / "catalog" / "pandas.json.gz"
CACHE = ROOT / "tools" / ".cache"
REFERENCE = (
    "https://raw.githubusercontent.com/pandas-dev/pandas/v{version}/doc/source/reference/{page}.rst"
)
PAGES = ("frame", "series", "groupby", "window", "resampling", "indexing", "general_functions")
FORMAT = 1
_SECTION = re.compile(
    r"\n\s*(?:Parameters|Returns|Yields|Raises|See Also|Notes|Examples|Attributes|Methods)\n\s*-{3,}"
)
_UNDERLINE = set("=-~^")


# ---- tiny data and the owners ----------------------------------------------------------------
def tiny() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "a": [1, 2, 3, 4],
            "b": [1.5, 2.5, np.nan, 4.0],
            "s": pd.array(["x", "y", "z", "x"], dtype="str"),
            "t": pd.date_range("2020-01-01", periods=4, freq="D"),
            "c": pd.Categorical(["u", "v", "u", "v"]),
        }
    )


def _frame():
    d = tiny()
    return d, d


def _series():
    s = tiny()["b"].copy()
    return s, s


def _df_groupby():
    d = tiny()[["a", "b", "c"]].copy()
    return d.groupby("c", observed=True), d


def _series_groupby():
    d = tiny()[["a", "b", "c"]].copy()
    return d.groupby("c", observed=True)["b"], d


def _resampler():
    d = tiny()[["a", "b", "t"]].set_index("t")
    return d.resample("2D"), d


def _numeric():
    return tiny()[["a", "b"]].copy()


def _rolling():
    d = _numeric()
    return d.rolling(2), d


def _expanding():
    d = _numeric()
    return d.expanding(), d


def _ewm():
    d = _numeric()
    return d.ewm(com=0.5), d


def _index():
    i = pd.Index(["x", "y", "z", "x"])
    return i, i


def _str():
    s = tiny()["s"].copy()
    return s.str, s


def _dt():
    s = tiny()["t"].copy()
    return s.dt, s


def _cat():
    s = tiny()["c"].copy()
    return s.cat, s


# owner -> (API reference prefix, factory returning (object, what to watch for mutation))
OWNERS: dict[str, tuple[str, Callable[[], tuple[Any, Any]]]] = {
    "DataFrame": ("DataFrame.", _frame),
    "Series": ("Series.", _series),
    "DataFrameGroupBy": ("DataFrameGroupBy.", _df_groupby),
    "SeriesGroupBy": ("SeriesGroupBy.", _series_groupby),
    "Resampler": ("Resampler.", _resampler),
    "Rolling": ("Rolling.", _rolling),
    "Expanding": ("Expanding.", _expanding),
    "ExponentialMovingWindow": ("ExponentialMovingWindow.", _ewm),
    "Index": ("Index.", _index),
    "str": ("Series.str.", _str),
    "dt": ("Series.dt.", _dt),
    "cat": ("Series.cat.", _cat),
}

# Arguments for probing methods that need some (the rest are called with none).
PROBES: dict[str, dict[str, tuple[tuple[Any, ...], dict[str, Any]]]] = {
    "DataFrame": {
        "groupby": ((), {"by": "c", "observed": True}),
        "merge": ((tiny(),), {"on": "a"}),
        "join": ((tiny()[["a"]].rename(columns={"a": "z"}),), {}),
        "sort_values": ((), {"by": "a"}),
        "drop": ((), {"columns": ["a"]}),
        "rename": ((), {"columns": {"a": "x"}}),
        "astype": ((), {"dtype": {"a": "float64"}}),
        "insert": ((0, "z", 1), {}),
        "pop": (("a",), {}),
        "update": ((pd.DataFrame({"a": [9, 9, 9, 9]}),), {}),
        "pivot_table": ((), {"index": "c", "values": "a", "observed": True}),
        "pivot": ((), {"columns": "s", "values": "a"}),
        "set_index": (("a",), {}),
        "apply": ((len,), {}),
        "agg": (("count",), {}),
        "aggregate": (("count",), {}),
        "where": ((tiny().notna(),), {}),
        "mask": ((tiny().isna(),), {}),
        "isin": (([1],), {}),
        "nlargest": ((2, "a"), {}),
        "nsmallest": ((2, "a"), {}),
        "explode": (("a",), {}),
        "select_dtypes": ((), {"include": "number"}),
        "get": (("a",), {}),
        "filter": ((), {"items": ["a"]}),
        "fillna": ((0,), {}),
        "replace": ((1, 2), {}),
        "rolling": ((2,), {}),
        "ewm": ((), {"com": 0.5}),
        "melt": ((), {"id_vars": ["a"], "value_vars": ["b"]}),
        "sample": ((), {"n": 2, "random_state": 0}),
        "assign": ((), {"z": 1}),
        "reindex": ((), {"index": [0, 1]}),
        "set_axis": ((["p", "q", "r", "s", "u"],), {"axis": 1}),
        "combine_first": ((tiny(),), {}),
        "compare": ((tiny().assign(a=[0, 2, 3, 4]),), {}),
        "xs": ((0,), {}),
        "add_prefix": (("p_",), {}),
        "add_suffix": (("_s",), {}),
    },
    "Series": {
        "map": ((str,), {}),
        "apply": ((abs,), {}),
        "astype": (("float64",), {}),
        "isin": (([1.5],), {}),
        "fillna": ((0,), {}),
        "replace": ((1.5, 2.0), {}),
        "where": ((pd.Series([True, False, True, True]),), {}),
        "mask": ((pd.Series([True, False, True, True]),), {}),
        "rolling": ((2,), {}),
        "ewm": ((), {"com": 0.5}),
        "groupby": ((pd.Series(["u", "v", "u", "v"]),), {"observed": True}),
        "nlargest": ((2,), {}),
        "nsmallest": ((2,), {}),
        "between": ((1, 3), {}),
        "clip": ((1, 3), {}),
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "transform": (("abs",), {}),
        "rename": (("z",), {}),
        "sample": ((), {"n": 2, "random_state": 0}),
        "set_axis": (([9, 8, 7, 6],), {}),
        "reindex": (([0, 1],), {}),
        "combine_first": ((pd.Series([0.0, 0.0, 0.0, 0.0]),), {}),
        "compare": ((pd.Series([1.5, 0.0, np.nan, 4.0]),), {}),
        "update": ((pd.Series([9.0]),), {}),
        "get": ((0,), {}),
        "xs": ((0,), {}),
        "add_prefix": (("p_",), {}),
        "add_suffix": (("_s",), {}),
    },
    "DataFrameGroupBy": {
        "get_group": (("u",), {}),
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "transform": (("sum",), {}),
        "apply": ((len,), {}),
        "filter": ((bool,), {}),
        "nth": ((0,), {}),
        "rolling": ((2,), {}),
        "take": (([0],), {}),
    },
    "SeriesGroupBy": {
        "get_group": (("u",), {}),
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "transform": (("sum",), {}),
        "apply": ((len,), {}),
        "filter": ((bool,), {}),
        "nth": ((0,), {}),
        "rolling": ((2,), {}),
        "take": (([0],), {}),
    },
    "Resampler": {
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "transform": (("sum",), {}),
        "apply": (("sum",), {}),
    },
    "Rolling": {
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "apply": ((np.sum,), {"raw": True}),
        "quantile": ((0.5,), {}),
    },
    "Expanding": {
        "agg": (("sum",), {}),
        "aggregate": (("sum",), {}),
        "apply": ((np.sum,), {"raw": True}),
        "quantile": ((0.5,), {}),
    },
    "Index": {
        "isin": ((["x"],), {}),
        "map": ((str.upper,), {}),
        "astype": (("str",), {}),
        "rename": (("z",), {}),
        "drop": ((["x"],), {}),
        "insert": ((0, "w"), {}),
        "append": ((pd.Index(["q"]),), {}),
        "union": ((pd.Index(["x", "q"]),), {}),
        "intersection": ((pd.Index(["x", "q"]),), {}),
        "difference": ((pd.Index(["x", "q"]),), {}),
        "symmetric_difference": ((pd.Index(["x", "q"]),), {}),
        "get_loc": (("y",), {}),
        "where": ((np.array([True, False, True, True]),), {}),
        "putmask": ((np.array([True, False, False, False]), "q"), {}),
        "set_names": (("n",), {}),
        "fillna": (("q",), {}),
        "equals": ((pd.Index(["x"]),), {}),
        "identical": ((pd.Index(["x"]),), {}),
        "get_indexer": ((["x"],), {}),
        "take": (([0],), {}),
        "repeat": ((2,), {}),
        "delete": ((0,), {}),
    },
    "str": {
        "contains": (("x",), {}),
        "startswith": (("x",), {}),
        "endswith": (("x",), {}),
        "replace": (("x", "y"), {}),
        "pad": ((5,), {}),
        "center": ((5,), {}),
        "ljust": ((5,), {}),
        "rjust": ((5,), {}),
        "zfill": ((5,), {}),
        "repeat": ((2,), {}),
        "get": ((0,), {}),
        "find": (("x",), {}),
        "rfind": (("x",), {}),
        "count": (("x",), {}),
        "match": (("x",), {}),
        "fullmatch": (("x",), {}),
        "extract": ((r"(x)",), {}),
        "extractall": ((r"(x)",), {}),
        "findall": (("x",), {}),
        "wrap": ((2,), {}),
        "join": (("-",), {}),
        "encode": (("utf-8",), {}),
        "translate": (({ord("x"): "y"},), {}),
        "removeprefix": (("x",), {}),
        "removesuffix": (("x",), {}),
        "normalize": (("NFC",), {}),
    },
    "dt": {
        "strftime": (("%Y",), {}),
        "round": (("D",), {}),
        "floor": (("D",), {}),
        "ceil": (("D",), {}),
        "tz_localize": (("UTC",), {}),
        "to_period": (("M",), {}),
        "as_unit": (("s",), {}),
    },
    "cat": {
        "rename_categories": ((["p", "q"],), {}),
        "reorder_categories": ((["v", "u"],), {}),
        "add_categories": ((["w"],), {}),
        "remove_categories": ((["u"],), {}),
        "set_categories": ((["u", "v", "w"],), {}),
    },
}

# Probing runs every other member, policy-denied mutators included (to record ``mutates``).
NEVER_CALL = frozenset(
    {"to_clipboard", "plot", "hist", "boxplot", "style", "info", "pipe", "eval", "query"}
)
SAME_AS_OWNER = frozenset(
    {"add", "sub", "mul", "div", "truediv", "floordiv", "mod", "pow", "radd", "rsub", "rmul",
     "rdiv", "rtruediv", "rfloordiv", "rmod", "rpow", "eq", "ne", "lt", "le", "gt", "ge",
     "combine", "dot"}
)  # fmt: skip
RETURNS = {"resample": "Resampler", "expanding": "Window", "rolling": "Window", "ewm": "Window"}
FUNCTION_RETURNS = {
    "concat": "DataFrame", "merge": "DataFrame", "merge_asof": "DataFrame",
    "merge_ordered": "DataFrame", "to_datetime": "Series", "to_numeric": "Series",
    "to_timedelta": "Series", "cut": "Series", "qcut": "Series", "get_dummies": "DataFrame",
    "from_dummies": "DataFrame", "crosstab": "DataFrame", "melt": "DataFrame",
    "pivot": "DataFrame", "pivot_table": "DataFrame", "wide_to_long": "DataFrame",
    "isna": "Series", "notna": "Series", "unique": "Array", "factorize": "Value",
    "date_range": "Index", "period_range": "Index", "timedelta_range": "Index",
    "interval_range": "Index",
}  # fmt: skip
ROWWISE = frozenset(
    {"head", "tail", "astype", "fillna", "isna", "notna", "isnull", "notnull", "abs", "round",
     "clip", "where", "mask", "replace", "rename", "drop", "assign", "filter", "select_dtypes",
     "copy", "to_frame", "dropna", "between", "isin", "map", "add_prefix", "add_suffix",
     "convert_dtypes", "infer_objects", *SAME_AS_OWNER}
)  # fmt: skip
SAMPLED = frozenset(
    {"describe", "mean", "median", "std", "var", "sum", "min", "max", "count", "nunique",
     "quantile", "sem", "skew", "kurt", "prod", "any", "all"}
)  # fmt: skip

COLUMNS = frozenset({"by", "subset", "on", "left_on", "right_on", "id_vars", "value_vars"})
FRAMES = frozenset({"other", "right", "objs", "left"})
FREQ = frozenset({"freq", "rule", "offset"})
FUNCS = frozenset({"func", "aggfunc", "arg"})


# ---- the API reference ----------------------------------------------------------------------
def _page(version: str, page: str) -> str:
    path = CACHE / f"pandas-{version}" / f"{page}.rst"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = REFERENCE.format(version=version, page=page)
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed https URL
            path.write_bytes(response.read())
    return path.read_text(encoding="utf-8")


def reference_sections(version: str) -> dict[str, str]:
    """'DataFrame.head' -> 'Indexing, iteration' for every entry of the API reference."""
    out: dict[str, str] = {}
    for page in PAGES:
        lines = _page(version, page).splitlines()
        section, in_summary = page, False
        for i, line in enumerate(lines):
            under = lines[i + 1].strip() if i + 1 < len(lines) else ""
            text = line.strip()
            heading = (
                text
                and not line.startswith(" ")
                and under
                and set(under) <= _UNDERLINE
                and len(under) >= len(text)
            )
            if heading:
                section, in_summary = text.replace("``", ""), False
                continue
            if text.startswith(".. autosummary::"):
                in_summary = True
                continue
            if in_summary:
                if not text or text.startswith(":"):
                    continue
                if not line.startswith("   "):
                    in_summary = False
                    continue
                out.setdefault(text, section)
    return out


# ---- members ----------------------------------------------------------------------------------
def member_doc(raw: Any) -> str:
    for obj in (raw, getattr(raw, "fget", None), getattr(raw, "__func__", None), getattr(raw, "_accessor", None)):
        doc = getattr(obj, "__doc__", None) if obj is not None else None
        if isinstance(doc, str) and doc.strip():
            return doc
    return ""


def deprecated(doc: str) -> bool:
    head = _SECTION.split(doc, maxsplit=1)[0]
    return ".. deprecated::" in head and not re.search(r"\.\. deprecated::[^\n]*\n\s*This keyword", head)


def summary(doc: str) -> str:
    para: list[str] = []
    for line in inspect.cleandoc(doc or "").splitlines():
        if not line.strip():
            if para:
                break
            continue
        para.append(line.strip())
    text = " ".join(para)
    return text if len(text) <= 240 else text[:239] + "…"


def member_kind(raw: Any) -> str:
    if isinstance(raw, (classmethod, staticmethod)):
        return "classmethod"
    if type(raw).__name__ in {"Accessor", "CachedAccessor"}:
        return "accessor"
    functions = (types.FunctionType, types.BuiltinFunctionType, types.MethodDescriptorType, types.WrapperDescriptorType)
    if isinstance(raw, functions):
        return "method"
    if isinstance(raw, property) or hasattr(type(raw), "__get__"):
        return "property"
    return "method" if callable(raw) else "attribute"


def signature(func: Any) -> inspect.Signature | None:
    try:
        import annotationlib

        return inspect.signature(func, annotation_format=annotationlib.Format.STRING)
    except ImportError:
        pass
    except (TypeError, ValueError):
        return None
    try:
        return inspect.signature(func)
    except (TypeError, ValueError):
        return None


def numpydoc_types(func: Any) -> dict[str, str]:
    try:
        from numpydoc.docscrape import NumpyDocString
    except ImportError:
        return {}
    out: dict[str, str] = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            parsed = NumpyDocString(getattr(func, "__doc__", None) or "")
        except Exception:
            return {}
    for p in parsed["Parameters"] + parsed["Other Parameters"]:
        for name in p.name.split(","):
            out[name.strip().lstrip("*")] = p.type
    return out


def choices_of(annotation: str, doc_type: str) -> list[Any]:
    match = re.search(r"Literal\[(.+?)\]", annotation)
    candidates = [match.group(1)] if match else []
    braces = re.search(r"\{([^{}]*)\}", doc_type or "")
    if braces:
        candidates.append(re.sub(r"[`*]", "", braces.group(1)))
    for body in candidates:
        try:
            values = ast.literal_eval(f"[{body}]")
        except (ValueError, SyntaxError):
            continue
        return [v for v in values if isinstance(v, (str, int, float, bool)) or v is None]
    return []


def widget(name: str, annotation: str, default: Any, choices: list[Any]) -> str:
    plain = annotation.replace(" ", "")
    if choices:
        return "choice"
    if name == "axis":
        return "axis"
    if name in COLUMNS:
        return "columns"
    if name in {"column", "col"}:
        return "column"
    if name in FRAMES:
        return "frame"
    if name == "dtype":
        return "dtype"
    if name in FREQ:
        return "freq"
    if name in FUNCS:
        return "func"
    if isinstance(default, bool) or plain in ("bool", "bool|None", "bool_t"):
        return "bool"
    if isinstance(default, int) or plain in ("int", "int|None"):
        return "int"
    if isinstance(default, float) or plain in ("float", "float|None"):
        return "float"
    if isinstance(default, str) or plain in ("str", "str|None"):
        return "text"
    return "value"


def params_of(func: Any) -> list[dict[str, Any]]:
    sig = signature(func)
    if sig is None:
        return []
    doc_types = numpydoc_types(func)
    out = []
    for p in sig.parameters.values():
        if p.name == "self":
            continue
        annotation = p.annotation if isinstance(p.annotation, str) else (
            "" if p.annotation is inspect.Parameter.empty else inspect.formatannotation(p.annotation)
        )
        entry: dict[str, Any] = {"name": p.name, "annotation": annotation}
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            entry.update(variadic="*" if p.kind is p.VAR_POSITIONAL else "**", widget="value")
            out.append(entry)
            continue
        default = None if p.default is p.empty else p.default
        choices = choices_of(annotation, doc_types.get(p.name, ""))
        entry["widget"] = widget(p.name, annotation, default, choices)
        entry["required"] = p.default is p.empty
        if choices:
            entry["choices"] = choices
        if p.default is not p.empty:
            try:
                entry["default"] = encode_scalar(p.default)
            except (OpError, TypeError, ValueError):
                entry["default"] = {"$repr": repr(p.default)[:80]}
        out.append(entry)
    return out


# ---- probes -----------------------------------------------------------------------------------
def returns_kind(value: Any) -> str:
    from pandas.api.typing import (
        DataFrameGroupBy,
        Expanding,
        ExponentialMovingWindow,
        Resampler,
        Rolling,
        SeriesGroupBy,
        Window,
    )

    if value is None:
        return "None"
    for kind, types_ in (
        ("DataFrame", pd.DataFrame),
        ("Series", pd.Series),
        ("Index", pd.Index),
        ("GroupBy", (DataFrameGroupBy, SeriesGroupBy)),
        ("Resampler", Resampler),
        ("Window", (Rolling, Expanding, ExponentialMovingWindow, Window)),
        ("Array", np.ndarray),
    ):
        if isinstance(value, types_):
            return kind
    return "Value"


def unchanged(before: Any, after: Any) -> bool:
    try:
        if isinstance(before, pd.DataFrame):
            return (
                before.columns.equals(after.columns)
                and before.index.equals(after.index)
                and before.dtypes.equals(after.dtypes)
                and before.equals(after)
            )
        if isinstance(before, pd.Series):
            return before.index.equals(after.index) and before.dtype == after.dtype and before.equals(after)
        if isinstance(before, pd.Index):
            return before.dtype == after.dtype and before.equals(after)
    except Exception:
        return False
    return True


def _no_required_args(bound: Any) -> bool:
    sig = signature(bound)
    if sig is None:
        return False
    return all(
        p.default is not p.empty or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        for p in sig.parameters.values()
    )


def probe(owner: str, name: str, kind: str) -> tuple[str, bool]:
    """(return kind, mutates) from running the member on tiny data."""
    writes = name.startswith("to_") and not method_allowed(name)  # IO: never run
    if kind == "classmethod" or writes or name in NEVER_CALL:
        return "unknown", False
    instance, watch = OWNERS[owner][1]()
    before = copy.deepcopy(watch)
    try:
        with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter("ignore")
            if kind != "method":
                value = getattr(instance, name)
            else:
                bound = getattr(instance, name)
                call = PROBES.get(owner, {}).get(name)
                if call is not None:
                    value = bound(*call[0], **call[1])
                elif _no_required_args(bound):
                    value = bound()
                else:
                    return "unknown", False
    except Exception:
        return "unknown", not unchanged(before, watch)
    return returns_kind(value), not unchanged(before, watch)


def preview_policy(owner: str, name: str) -> str:
    if owner in ("str", "dt", "cat") or name in ROWWISE:
        return "rowwise"
    return "sampled_stat" if name in SAMPLED else "global"


def member_entry(owner: str, name: str, raw: Any, sections: dict[str, str]) -> dict[str, Any] | None:
    doc = member_doc(raw)
    if deprecated(doc):
        return None
    prefix = OWNERS[owner][0]
    kind = member_kind(raw)
    entry: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "category": sections.get(prefix + name, "Other"),
        "summary": summary(doc),
        "allowed": method_allowed(name),
        "preview": preview_policy(owner, name),
    }
    if kind in ("method", "classmethod"):
        func = raw.__func__ if isinstance(raw, (classmethod, staticmethod)) else raw
        entry["params"] = params_of(func)
    returns, mutates = probe(owner, name, kind)
    if returns == "unknown" and name in SAME_AS_OWNER and owner in ("DataFrame", "Series", "Index"):
        returns = owner
    entry["returns"] = RETURNS.get(name, returns) if returns == "unknown" else returns
    entry["mutates"] = mutates
    return entry


def function_entry(name: str, sections: dict[str, str]) -> dict[str, Any]:
    func = getattr(pd, name)
    doc = func.__doc__ or ""
    return {
        "name": name,
        "kind": "function",
        "category": sections.get(name, "Other"),
        "summary": summary(doc),
        "allowed": True,
        "preview": "global",
        "params": params_of(func),
        "returns": FUNCTION_RETURNS.get(name, "unknown"),
        "mutates": False,
    }


def main() -> None:
    sections = reference_sections(pd.__version__)
    owners: dict[str, Any] = {}
    for owner, (_prefix, factory) in OWNERS.items():
        cls = type(factory()[0])
        members, dropped = [], []
        for name in sorted(dir(cls)):
            if name.startswith("_"):
                continue
            try:
                raw = inspect.getattr_static(cls, name)
            except AttributeError:
                continue
            entry = member_entry(owner, name, raw, sections)
            if entry is None:
                dropped.append(name)
            else:
                members.append(entry)
        owners[owner] = {"members": members, "deprecated": dropped}
    owners["pd"] = {
        "members": [function_entry(n, sections) for n in sorted(ALLOWED_PD_FUNCS)],
        "deprecated": [],
    }
    data = {"format": FORMAT, "pandas_version": pd.__version__, "owners": owners}
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    OUT.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    count = sum(len(o["members"]) for o in owners.values())
    print(f"wrote {OUT.relative_to(ROOT)}: {count} members, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write the runtime reader**

<!-- file: src/framelab/catalog/__init__.py -->
```python
"""The pandas catalog: every member framelab can offer, with category, parameters, return kind,
mutation flag and preview policy.

``tools/gen_catalog.py`` builds ``pandas.json.gz`` from the reference pandas; this module reads
it. Members a newer pandas adds still show up, found by introspection, under "Other".
"""

from __future__ import annotations

import functools
import gzip
import inspect
import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from ..ops.policy import method_allowed

__all__ = ["OTHER", "Catalog", "Member", "Param", "load", "owner_types"]

OTHER = "Other"


@dataclass(frozen=True)
class Param:
    name: str
    widget: str = "value"
    required: bool = False
    default: Any = None
    choices: tuple[Any, ...] = ()
    annotation: str = ""
    variadic: str = ""

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "widget": self.widget,
            "required": self.required,
            "annotation": self.annotation,
        }
        if not self.required and not self.variadic:
            out["default"] = self.default
        if self.choices:
            out["choices"] = list(self.choices)
        if self.variadic:
            out["variadic"] = self.variadic
        return out


@dataclass(frozen=True)
class Member:
    owner: str
    name: str
    kind: str
    category: str = OTHER
    summary: str = ""
    params: tuple[Param, ...] = ()
    returns: str = "unknown"
    mutates: bool = False
    preview: str = "global"
    allowed: bool = True
    generated: bool = True

    def describe(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "name": self.name,
            "kind": self.kind,
            "category": self.category,
            "summary": self.summary,
            "params": [p.describe() for p in self.params],
            "returns": self.returns,
            "mutates": self.mutates,
            "preview": self.preview,
            "allowed": self.allowed,
            "generated": self.generated,
        }


def _param(raw: dict[str, Any]) -> Param:
    return Param(
        name=raw["name"],
        widget=raw.get("widget", "value"),
        required=raw.get("required", False),
        default=raw.get("default"),
        choices=tuple(raw.get("choices") or ()),
        annotation=raw.get("annotation", ""),
        variadic=raw.get("variadic", ""),
    )


def _member(owner: str, raw: dict[str, Any]) -> Member:
    return Member(
        owner=owner,
        name=raw["name"],
        kind=raw["kind"],
        category=raw.get("category", OTHER),
        summary=raw.get("summary", ""),
        params=tuple(_param(p) for p in raw.get("params", [])),
        returns=raw.get("returns", "unknown"),
        mutates=raw.get("mutates", False),
        preview=raw.get("preview", "global"),
        allowed=raw.get("allowed", True),
    )


@functools.cache
def owner_types() -> dict[str, type]:
    """The runtime class behind every owner (used for members missing from the file)."""
    import pandas as pd
    from pandas.api.typing import (
        DataFrameGroupBy,
        Expanding,
        ExponentialMovingWindow,
        Rolling,
        SeriesGroupBy,
    )

    t = pd.DataFrame(
        {
            "s": pd.array(["x"], dtype="str"),
            "t": pd.to_datetime(["2020-01-01"]),
            "c": pd.Categorical(["u"]),
        }
    )
    return {
        "DataFrame": pd.DataFrame,
        "Series": pd.Series,
        "Index": pd.Index,
        "DataFrameGroupBy": DataFrameGroupBy,
        "SeriesGroupBy": SeriesGroupBy,
        "Resampler": type(t.set_index("t").resample("D")),
        "Rolling": Rolling,
        "Expanding": Expanding,
        "ExponentialMovingWindow": ExponentialMovingWindow,
        "str": type(t["s"].str),
        "dt": type(t["t"].dt),
        "cat": type(t["c"].cat),
    }


def _introspect(owner: str, name: str) -> Member | None:
    cls = owner_types().get(owner)
    if cls is None or name.startswith("_"):
        return None
    try:
        raw = inspect.getattr_static(cls, name)
    except AttributeError:
        return None
    doc = inspect.getdoc(raw) or ""
    summary = " ".join(doc.strip().split("\n\n", 1)[0].split())[:240]
    method = inspect.isfunction(raw) or inspect.ismethoddescriptor(raw) or inspect.isbuiltin(raw)
    params: tuple[Param, ...] = ()
    if method:
        try:
            sig = inspect.signature(raw)
        except (TypeError, ValueError):
            sig = None
        if sig is not None:
            variadic = {inspect.Parameter.VAR_POSITIONAL: "*", inspect.Parameter.VAR_KEYWORD: "**"}
            params = tuple(
                Param(
                    p.name,
                    required=p.default is p.empty and p.kind not in variadic,
                    variadic=variadic.get(p.kind, ""),
                )
                for p in sig.parameters.values()
                if p.name != "self"
            )
    kind = "method" if method else "property"
    return Member(owner, name, kind, OTHER, summary, params, allowed=method_allowed(name), generated=False)


class Catalog:
    def __init__(self, data: dict[str, Any]) -> None:
        self.pandas_version: str = data["pandas_version"]
        self._members: dict[str, dict[str, Member]] = {
            owner: {m["name"]: _member(owner, m) for m in body["members"]}
            for owner, body in data["owners"].items()
        }
        self._deprecated = {owner: set(body.get("deprecated", [])) for owner, body in data["owners"].items()}

    @property
    def owners(self) -> list[str]:
        return list(self._members)

    def member(self, owner: str, name: str) -> Member | None:
        found = self._members.get(owner, {}).get(name)
        if found is not None or name in self._deprecated.get(owner, ()):
            return found
        return _introspect(owner, name)

    def members(self, owner: str) -> list[Member]:
        known = self._members.get(owner, {})
        out = list(known.values())
        cls = owner_types().get(owner)
        if cls is not None:
            skip = set(known) | self._deprecated.get(owner, set())
            for name in sorted(dir(cls)):
                if not name.startswith("_") and name not in skip:
                    extra = _introspect(owner, name)
                    if extra is not None:
                        out.append(extra)
        return out


@functools.cache
def load() -> Catalog:
    raw = resources.files(__package__).joinpath("pandas.json.gz").read_bytes()
    return Catalog(json.loads(gzip.decompress(raw)))
```

In `src/framelab/transport/methods.py`:

```python
    def catalog_members(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        from ..catalog import load

        catalog = load()
        owner = params.get("owner")
        if owner not in catalog.owners:
            raise BadRequest(f"owner must be one of {', '.join(catalog.owners)}")
        members = [m.describe() for m in catalog.members(owner)]
        return {"pandas_version": catalog.pandas_version, "members": members}

    dispatcher.register("catalog.members", catalog_members)
```

Add `tools/.cache/` to `.gitignore`.

- [ ] **Step 5: Generate the file and run the tests**

Run: `.venv/bin/python tools/gen_catalog.py && .venv/bin/python -m pytest tests/test_catalog.py -q`
Expected: the generator prints `wrote src/framelab/catalog/pandas.json.gz: N members, K KB` (N ≈ 1500–2000, K < 400); tests PASS. If a category assertion fails, check the section title in `tools/.cache/pandas-*/…rst` and fix the parser, not the test.

- [ ] **Step 6: Commit**

```bash
git add tools/gen_catalog.py src/framelab/catalog tests/test_catalog.py .gitignore src/framelab/transport/methods.py
git commit -m "Generated pandas catalog: categories, parameters, return kinds, mutation, preview policy"
```

---

### Task 10: Export the whole session to `.py` and `.ipynb`

**Files:**
- Create: `src/framelab/codegen/export.py`, `src/framelab/session/paths.py`, `tests/test_export.py`
- Modify: `src/framelab/codegen/chain.py` (`root_mode` parameter), `src/framelab/session/figures.py` (`figure_display`, `export` uses `output_path`), `src/framelab/session/core.py` (`export`), `src/framelab/transport/methods.py` (`session.export`)

**Interfaces:**
- Consumes: `pipeline_lines`, `chained_lines`, `render_op`, `used_modules`, `import_lines`, `restyle` (Tasks 1–2).
- Produces: `session_script(session, style=None) -> str`, `session_notebook(session, style=None) -> dict` (nbformat 4.5), `output_path(path, suffixes) -> Path`, `FigureStore.figure_display(fid) -> str`, `Session.export(fmt="py" | "ipynb", path=None) -> {"text", "path"}`, `chained_lines(session, targets, style, root_mode="origin")`, protocol `session.export {format, path?}` → `{"text", "path"}`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/test_export.py -->
```python
import json
import os
import pickle
import subprocess
import sys

import nbformat
import pandas as pd
import pytest
from test_fidelity import assert_same, make_frames

from framelab.errors import BadRequest
from framelab.naming import RootSpec
from framelab.ops.build import call, col, getitem, gt, mul, node, ref_col, setcol, where
from framelab.options import build_default_registry
from framelab.session import NodeError, Session


def build(options=None):
    registry = build_default_registry()
    for key, value in (options or {}).items():
        registry.set(key, value)
    ventas, clientes = make_frames()
    s = Session([RootSpec("ventas", ventas), RootSpec("clientes", clientes)], registry)
    a = s.apply(where("n1", gt(col("monto"), 50)))
    b = s.apply(setcol(a.id, "total", mul(col("monto"), col("cantidad"))))
    c = s.apply(call(b.id, "groupby", by=ref_col("pais")))
    d = s.apply(getitem(c.id, "total"))
    e = s.apply(call(d.id, "sum"), name="por_pais")
    merged = s.apply(call("n1", "merge", node("n2"), on="id", how="left"))
    bad = s.apply(getitem("n1", "no_existe"))
    fig = s.plots.create(e.id)
    spec = fig["spec"]
    spec["axes"][0]["layers"] = [{"kind": "bar", "source": e.id}]
    s.plots.update(fig["id"], spec)
    s.wait(e.id)
    s.wait(merged.id)
    with pytest.raises(NodeError):
        s.wait(bad.id)
    return s


def run_script(script, tmp_path):
    ventas, clientes = make_frames()
    ventas.to_pickle(tmp_path / "v.pkl")
    clientes.to_pickle(tmp_path / "c.pkl")
    out = tmp_path / "out.pkl"
    program = (
        "import pandas as pd\n"
        f"ventas = pd.read_pickle({str(tmp_path / 'v.pkl')!r})\n"
        f"clientes = pd.read_pickle({str(tmp_path / 'c.pkl')!r})\n"
        f"{script}\n"
        "import pickle\n"
        "found = {k: v for k, v in dict(globals()).items()"
        " if not k.startswith('_') and isinstance(v, (pd.DataFrame, pd.Series))}\n"
        f"pickle.dump(found, open({str(out)!r}, 'wb'))\n"
    )
    subprocess.run([sys.executable, "-c", program], check=True, env={**os.environ, "MPLBACKEND": "Agg"})
    with open(out, "rb") as fh:
        return pickle.load(fh)


@pytest.mark.parametrize(
    "options",
    [{}, {"code.style": "chained"}, {"code.filter_style": "query", "code.quote": "single"}],
)
def test_exported_script_reproduces_every_node(tmp_path, options):
    s = build(options)
    try:
        values = run_script(s.export("py")["text"], tmp_path)
        tables = ("DataFrame", "Series")  # what the script run pickles back
        ready = [
            n
            for n in s.nodes()
            if n.state.value == "ready" and not n.is_root and n.kind.value in tables
        ]
        if not options:
            assert {n.name for n in ready} <= set(values)
        assert "por_pais" in values
        for n in ready:
            if n.name in values:
                assert_same(s.wait(n.id), values[n.name])
    finally:
        s.close()


def test_script_layout():
    s = build()
    try:
        text = s.export("py")["text"]
        assert text.startswith(
            "# framelab session: ventas, clientes\n"
            "# Requires: ventas (DataFrame 6 × 7: id, fecha, pais, monto, cantidad, …)\n"
            "# Requires: clientes (DataFrame 4 × 2: id, nombre)\n\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n"
        )
        assert '# ventas_no_existe = ventas["no_existe"]\n# ↑ KeyError: \'no_existe\'' in text
        assert "fig_por_pais, ax_por_pais = plt.subplots(" in text
        assert text.endswith("plt.show()\n")
    finally:
        s.close()


def test_notebook_is_valid():
    s = build()
    try:
        notebook = json.loads(s.export("ipynb")["text"])
        nbformat.validate(nbformat.from_dict(notebook))
        kinds = [c["cell_type"] for c in notebook["cells"]]
        assert kinds[:3] == ["markdown", "markdown", "code"]
        assert any("por_pais = " in c["source"] for c in notebook["cells"])
        assert not any("plt.show()" in c["source"] for c in notebook["cells"])
    finally:
        s.close()


def test_export_writes_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = build()
    try:
        out = s.export("py", path="sesion.py")
        assert out["path"] == str(tmp_path / "sesion.py")
        assert (tmp_path / "sesion.py").read_text(encoding="utf-8") == out["text"]
        for bad in ("sesion.txt", "no/dir/x.py"):
            with pytest.raises(BadRequest):
                s.export("py", path=bad)
        with pytest.raises(BadRequest):
            s.export("csv")
    finally:
        s.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_export.py -q`
Expected: FAIL with `AttributeError: 'Session' object has no attribute 'export'`

- [ ] **Step 3: Implement**

<!-- file: src/framelab/session/paths.py -->
```python
"""Where framelab writes files the user asks for: relative paths are relative to the folder
Python runs in, exactly like the code framelab shows would write them."""

from __future__ import annotations

from pathlib import Path

from ..errors import BadRequest

__all__ = ["output_path"]


def output_path(path: object, suffixes: tuple[str, ...]) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise BadRequest("path must be a file name")
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    if target.suffix.lower() not in suffixes:
        raise BadRequest(f"the file name must end in {suffixes[0]}")
    if target.is_dir() or not target.parent.is_dir():
        raise BadRequest(f"cannot write {target}: the folder does not exist")
    return target
```

<!-- file: src/framelab/codegen/export.py -->
```python
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
    out = "\n".join([f"# framelab session: {_roots(session)}", *(f"# Requires: {n}" for n in needs)])
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
        sources.append(("markdown", f"Define these variables before running the notebook:\n\n{listed}"))
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
```

`src/framelab/codegen/chain.py`: add `root_mode: str = "origin"` to `chained_lines` and pass it to `root_line`.

`src/framelab/session/figures.py`: move the figure-code part of `code()` into

```python
    def figure_display(self, fid: str, timeout: float = 30.0) -> str:
        """The figure's own code (unstyled), with its savefig line when it was exported."""
        with self._lock:
            doc = self._doc(fid)
            exported = doc.exported
        code, _ = self._code(doc, timeout)
        savefig = None
        if exported:
            args = [emit_literal(exported["path"]), f"dpi={exported['dpi']}"]
            if exported.get("transparent"):
                args.append("transparent=True")
            savefig = f"{code.fig_var}.savefig({', '.join(args)})"
        return code.display(savefig=savefig)
```

and let `code()` call it; replace the path checks in `export()` with `output_path(path, suffixes)`.

`src/framelab/session/core.py`:

```python
    def export(self, fmt: str = "py", path: str | None = None) -> dict[str, Any]:
        """The whole session as a script (``py``) or notebook (``ipynb``); written if ``path``."""
        from ..codegen.export import session_notebook, session_script
        from .paths import output_path

        if fmt == "py":
            text = session_script(self)
        elif fmt == "ipynb":
            text = json.dumps(session_notebook(self), ensure_ascii=False, indent=1) + "\n"
        else:
            raise BadRequest("format must be py or ipynb")
        written = None
        if path is not None:
            target = output_path(path, (f".{fmt}",))
            target.write_text(text, encoding="utf-8")
            written = str(target)
        return {"text": text, "path": written}
```

(`import json` and `from ..errors import BadRequest` at the top.) In `src/framelab/transport/methods.py`:

```python
    dispatcher.register(
        "session.export",
        lambda params, _b: session.export(params.get("format", "py"), path=params.get("path")),
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_export.py tests/test_plot.py tests/test_chain.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/framelab tests/test_export.py
git commit -m "Export the whole session as a Python script or a Jupyter notebook"
```

---

### Task 11: Autosave and `fl.open()`

**Files:**
- Create: `src/framelab/session/autosave.py`, `tests/test_autosave.py`, `tests/conftest.py`
- Modify: `src/framelab/options.py` (`general.autosave`), `src/framelab/session/core.py` (`autosaver`, `close`), `src/framelab/api.py` (`_show`, `_start_autosave`, `open`, `autosaves`), `src/framelab/__init__.py`, `README.md` (usage: `fl.open`)

**Interfaces:**
- Produces: `Autosaver(session, directory=None, *, delay=2.0, keep=20)` with `path`, `save() -> Path | None`, `flush()`, `close()`; `default_directory() -> Path` (honours `FRAMELAB_DATA_DIR`), `recent(directory=None) -> list[dict]`, `latest(directory=None) -> Path`; `fl.open(path="last", *, mode=None, **roots) -> Session`; `fl.autosaves() -> list[dict]`; `Session.autosaver`.

- [ ] **Step 1: Write the failing tests**

<!-- file: tests/conftest.py -->
```python
import pytest


@pytest.fixture(autouse=True)
def _framelab_data_dir(tmp_path_factory, monkeypatch):
    """Autosaves from tests never land in the real user data folder."""
    monkeypatch.setenv("FRAMELAB_DATA_DIR", str(tmp_path_factory.mktemp("framelab-data")))
```

<!-- file: tests/test_autosave.py -->
```python
import os
import time

import pandas as pd
import pytest

import framelab as fl
import framelab.api as api
from framelab.naming import RootSpec
from framelab.ops.build import call
from framelab.session import Session
from framelab.session.autosave import Autosaver, latest, recent
from framelab.session.document import from_document, load

VENTAS = pd.DataFrame({"pais": ["AR", "UY"], "monto": [1.0, 2.0]})


def wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def s():
    session = Session([RootSpec("ventas", VENTAS.copy())])
    yield session
    session.close()


def test_changes_are_saved_after_a_pause(s, tmp_path):
    saver = Autosaver(s, tmp_path, delay=0.05)
    try:
        head = s.apply(call("n1", "head", n=1), name="top")
        s.wait(head.id)
        assert wait_for(saver.path.exists)
        restored, problems = from_document(load(saver.path), {"ventas": VENTAS})
        assert problems == [] and restored.node(head.id).name == "top"
        restored.close()
    finally:
        saver.close()


def test_old_autosaves_are_pruned(s, tmp_path):
    for i in range(5):
        old = tmp_path / f"old{i}.framelab"
        old.write_text("{}")
        os.utime(old, (i, i))
    saver = Autosaver(s, tmp_path, delay=0.01, keep=3)
    try:
        assert saver.save() == saver.path
        assert len(list(tmp_path.glob("*.framelab"))) == 3 and saver.path.exists()
    finally:
        saver.close()


def test_autosave_failures_never_break_the_session(s, tmp_path, caplog):
    """Review focus 5: a failing save is logged, the session keeps working."""
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    saver = Autosaver(s, blocker / "sessions", delay=0.01)
    try:
        with caplog.at_level("WARNING", logger="framelab"):
            assert saver.save() is None
        assert "autosave failed" in caplog.text
        head = s.apply(call("n1", "head", n=1))
        pd.testing.assert_frame_equal(s.wait(head.id), VENTAS.head(1))
    finally:
        saver.close()


def test_recent_and_latest(s, tmp_path):
    saver = Autosaver(s, tmp_path)
    try:
        saver.save()
        [item] = recent(tmp_path)
        assert item["roots"] == ["ventas"] and item["nodes"] == 1
        assert latest(tmp_path) == saver.path
        with pytest.raises(FileNotFoundError):
            latest(tmp_path / "empty")
    finally:
        saver.close()


def test_fl_open_reopens_the_last_autosave(s, monkeypatch):
    saver = Autosaver(s)
    head = s.apply(call("n1", "head", n=1), name="top")
    s.wait(head.id)
    saver.save()
    saver.close()
    monkeypatch.setattr(api, "_show", lambda session, mode: session)
    reopened = fl.open("last", ventas=VENTAS)
    try:
        assert reopened.node("top").id == head.id
        assert reopened.autosaver is not None
        assert fl.autosaves()[0]["roots"] == ["ventas"]
    finally:
        reopened.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_autosave.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'framelab.session.autosave'`

- [ ] **Step 3: Implement**

<!-- file: src/framelab/session/autosave.py -->
```python
"""Autosave: the session document is written in the background a moment after each change.

Documents hold ops, names and figure specs, never data; ``fl.open("last", ventas=df)`` brings a
session back with the data passed again. A failing save is logged and never interrupts work.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import platformdirs

from .document import to_document

__all__ = ["Autosaver", "default_directory", "latest", "recent"]

log = logging.getLogger("framelab")
KEEP = 20


def default_directory() -> Path:
    override = os.environ.get("FRAMELAB_DATA_DIR")
    base = Path(override) if override else Path(platformdirs.user_data_dir("framelab"))
    return base / "sessions"


class Autosaver:
    def __init__(
        self,
        session: Any,
        directory: Path | str | None = None,
        *,
        delay: float = 2.0,
        keep: int = KEEP,
    ) -> None:
        self.session = session
        self.directory = Path(directory) if directory is not None else default_directory()
        self.delay = delay
        self.keep = keep
        self.path = self.directory / f"{time.strftime('%Y%m%d-%H%M%S')}-{session.id}.framelab"
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._dirty = False
        self._unsubscribe = session.subscribe(self._changed)

    def _changed(self, method: str, _params: dict[str, Any]) -> None:
        if not method.startswith(("node.", "figure.", "graph.")):
            return
        with self._lock:
            self._dirty = True
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.delay, self.save)
            self._timer.daemon = True
            self._timer.start()

    def save(self) -> Path | None:
        with self._lock:
            self._dirty = False
            self._timer = None
        try:
            document = to_document(self.session)
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, self.path)
            self._prune()
        except Exception:
            log.warning("framelab: autosave failed", exc_info=True)
            return None
        return self.path

    def _prune(self) -> None:
        files = sorted(self.directory.glob("*.framelab"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[self.keep :]:
            if old != self.path:
                with contextlib.suppress(OSError):
                    old.unlink()

    def flush(self) -> None:
        """Save now if something changed since the last save."""
        with self._lock:
            pending = self._dirty
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if pending:
            self.save()

    def close(self) -> None:
        self._unsubscribe()
        self.flush()


def recent(directory: Path | str | None = None) -> list[dict[str, Any]]:
    """Saved sessions, newest first."""
    folder = Path(directory) if directory is not None else default_directory()
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.framelab"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            nodes = document["graph"]["nodes"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        out.append(
            {
                "path": str(path),
                "saved": path.stat().st_mtime,
                "roots": [e["name"] for e in nodes if "source" in e],
                "nodes": len(nodes),
                "figures": len((document.get("figures") or {}).get("items", [])),
            }
        )
    return out


def latest(directory: Path | str | None = None) -> Path:
    items = recent(directory)
    if not items:
        raise FileNotFoundError("there is no saved framelab session yet")
    return Path(items[0]["path"])
```

`src/framelab/options.py`: add `Option("general.autosave", True, bool)`.

`src/framelab/session/core.py`: `self.autosaver: Any = None` in `__init__`; `close()` first does `if self.autosaver is not None: self.autosaver.close()`.

`src/framelab/api.py`: split `explore` so the display part is reusable:

```python
__all__ = ["autosaves", "explore", "last_session", "open"]


def _start_autosave(session: Session) -> None:
    if registry.get("general.autosave"):
        from .session.autosave import Autosaver

        session.autosaver = Autosaver(session)


def _show(session: Session, mode: str | None) -> Session:
    """Display a session: inline in notebooks, a window (blocking) from scripts."""
    global _last_session
    env = detect_env()
    resolved = resolve_mode(mode or registry.get("general.open_mode"), env)
    if resolved == "window" and env in INLINE_ENVS:
        warnings.warn(
            "opening a separate window from a notebook arrives in a later version; "
            "showing the workbench inline",
            stacklevel=3,
        )
        resolved = "inline"
    dispatcher = Dispatcher(session)
    _last_session = session
    if resolved == "inline":
        from .transport.widget import FramelabWidget

        widget = FramelabWidget(dispatcher, height=registry.get("general.inline_height"))
        session.widget = widget
        _display(widget)
    else:
        from .transport.server import FramelabServer

        title = f"framelab · {', '.join(n.name for n in session.nodes() if n.is_root)}"
        server = FramelabServer(dispatcher, _static_dir(), title=title)
        server.start()
        try:
            _open_window(server, title=title)
        finally:
            server.stop()
            if session.autosaver is not None:
                session.autosaver.flush()
    return session


def explore(*dfs: Any, name: str | None = None, mode: str | None = None, **named: Any) -> Session:
    """(docstring unchanged)"""
    if not dfs and not named:
        raise TypeError("explore() needs at least one DataFrame or Series")
    frame = user_frame(sys._getframe(1))
    try:
        specs = resolve_root_names(dfs, named, frame, explicit_name=name, callee=explore)
    finally:
        del frame
    session = Session(specs, registry)
    _start_autosave(session)
    return _show(session, mode)


def open(path: str | Path = "last", *, mode: str | None = None, **roots: Any) -> Session:  # noqa: A001
    """Reopen a saved or autosaved session with its data: ``fl.open("last", ventas=df)``."""
    from .session.autosave import latest
    from .session.document import from_document, load

    target = latest() if path == "last" else Path(path)
    session, problems = from_document(load(target), roots, registry)
    for message in problems:
        warnings.warn(message, stacklevel=2)
    _start_autosave(session)
    return _show(session, mode)


def autosaves() -> list[dict[str, Any]]:
    """Recently saved sessions, newest first (path, time, data names, sizes)."""
    from .session.autosave import recent

    return recent()
```

`src/framelab/__init__.py`: export `open` and `autosaves` next to `explore`. `README.md` (both languages, usage section): add

```python
fl.open("last", ventas=ventas)     # reopen the last autosaved session with its data
fl.autosaves()                     # recently saved sessions
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_autosave.py tests/test_api.py tests/test_document.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/framelab tests/test_autosave.py tests/conftest.py README.md
git commit -m "Autosave sessions in the background and reopen them with fl.open()"
```

---

### Task 12: Workbench hooks — undo/redo, cancel, retry, rename, clear, export, pins, force

**Files:**
- Create: `frontend/src/workbench/RenameDialog.tsx`
- Modify: `frontend/src/state/store.ts` (`renaming`, `askRename`), `frontend/src/app/App.tsx` (pins), `frontend/src/app/Shell.tsx` (`RenameDialog`), `frontend/src/workbench/Canvas.tsx` (tools + keys), `frontend/src/workbench/NodeMenu.tsx`, `frontend/src/workbench/NodeCard.tsx`, `frontend/src/workbench/CodePanel.tsx`, `frontend/src/workbench/OpForm.tsx`, `frontend/src/workbench/applyOp.ts`, `frontend/src/styles/app.css`, `frontend/src/i18n/locales/{es,en}.json`, `frontend/tests/e2e/workbench.e2e.mjs`

**Interfaces:**
- Consumes: protocol `graph.undo`, `graph.redo`, `graph.clear_failed`, `node.cancel`, `node.retry`, `node.rename`, `session.export`, `session.pins`, `node.apply {force}`; snapshot `history`; `NodeInfo.cancelling`; states `cancelled`/`freed` (generated types).
- Produces: `applyOp(rpc, op, opts?: { force?: boolean })`; store `renaming: string | null`, `askRename(id: string | null)`.

- [ ] **Step 1: Store, apply and rename dialog** — in `frontend/src/state/store.ts` add `renaming: string | null` (initial `null`) and `askRename: (renaming) => set({ renaming, menu: null })`; clear `renaming` in `setSnapshot` when that node disappears.

`frontend/src/workbench/applyOp.ts`:

```ts
export async function applyOp(rpc: Rpc, op: OpJson, opts: { force?: boolean } = {}): Promise<NodeInfo> {
  const params: Record<string, unknown> = { op: op as unknown as Record<string, unknown> };
  if (opts.force) params.force = true;
  const { result } = await rpc.request<{ node: NodeInfo }>("node.apply", params);
  return result.node;
}
```

<!-- file: frontend/src/workbench/RenameDialog.tsx -->
```tsx
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import { useAppStore } from "../state/context";
import { usePortalContainer } from "../ui/portal";

/** Rename a node: its variable in every piece of code; auto-named children follow. */
export function RenameDialog() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const nodeId = useAppStore((s) => s.renaming);
  const close = useAppStore((s) => s.askRename);
  const node = useAppStore((s) => s.snapshot?.nodes.find((n) => n.id === s.renaming) ?? null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setName(node?.name ?? "");
    setError(null);
  }, [nodeId]); // eslint-disable-line react-hooks/exhaustive-deps -- reset only when opening

  if (!nodeId || !node || !portal) return null;
  const submit = async () => {
    try {
      await rpc.request("node.rename", { id: nodeId, name });
      close(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };
  return createPortal(
    <div className="fl-overlay" onMouseDown={() => close(null)}>
      <form
        className="fl-dialog"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        onKeyDown={(e) => e.key === "Escape" && close(null)}
      >
        <div className="fl-dialog-title">{t("rename.title", { name: node.name })}</div>
        <input autoFocus className="fl-input fl-mono" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="fl-muted">{t("rename.help")}</div>
        {error ? <div className="fl-form-error">{error}</div> : null}
        <div className="fl-dialog-actions">
          <button type="button" className="fl-btn" onClick={() => close(null)}>
            {t("form.cancel")}
          </button>
          <button type="submit" className="fl-btn fl-btn-primary" disabled={!name.trim()}>
            {t("rename.confirm")}
          </button>
        </div>
      </form>
    </div>,
    portal,
  );
}
```

Render `<RenameDialog />` in `Shell.tsx` next to `<DeleteDialog />`.

- [ ] **Step 2: Node menu, card and canvas tools** — `NodeMenu.tsx`, in the "Nodo" group:

```tsx
            {node.state === "pending" || node.state === "computing" ? (
              <button type="button" className="fl-menu-item" onClick={() => void rpc.request("node.cancel", { id: node.id }).then(closeMenu)}>
                {t("menu.cancel")}
              </button>
            ) : null}
            {["error", "blocked", "cancelled"].includes(node.state) ? (
              <button type="button" className="fl-menu-item" onClick={() => void rpc.request("node.retry", { id: node.id }).then(closeMenu)}>
                {t("menu.retry")}
              </button>
            ) : null}
            {node.parents.length > 0 ? (
              <button type="button" className="fl-menu-item" onClick={() => askRename(node.id)}>
                {t("menu.rename")}
                <span className="fl-menu-more">F2</span>
              </button>
            ) : null}
```

`NodeCard.tsx`: show `t("node.cancelling")` in the meta line when `info.cancelling`; busy spinner also for `cancelling`.

`Canvas.tsx`: read `history = useAppStore((s) => s.snapshot?.history)`; render before the drop zones

```tsx
      <div className="fl-canvas-tools">
        <button type="button" className="fl-btn" disabled={!history?.can_undo} title={`${t("workbench.undo")} (Ctrl+Z)`} onClick={() => void rpc.request("graph.undo")}>
          ↶
        </button>
        <button type="button" className="fl-btn" disabled={!history?.can_redo} title={`${t("workbench.redo")} (Ctrl+Y)`} onClick={() => void rpc.request("graph.redo")}>
          ↷
        </button>
        {infos.some((n) => ["error", "blocked", "cancelled"].includes(n.state)) ? (
          <button type="button" className="fl-btn fl-btn-quiet-danger" onClick={() => void rpc.request("graph.clear_failed")}>
            {t("workbench.clear_failed")}
          </button>
        ) : null}
      </div>
```

and extend the window key handler: when not typing, `Ctrl/Cmd+Z` → `graph.undo`, `Ctrl/Cmd+Y` or `Ctrl/Cmd+Shift+Z` → `graph.redo` (with `preventDefault`), `F2` → `askRename(selectedId)` for non-root nodes, keeping Delete/Backspace as before.

- [ ] **Step 3: Export buttons, pins and force** — `CodePanel.tsx` toolbar, before the copy button:

```tsx
        <span className="fl-muted fl-hint-inline">{t("code.export_title")}</span>
        {(["py", "ipynb"] as const).map((format) => (
          <button key={format} type="button" className="fl-btn" onClick={() => void download(format)}>
            ↓ .{format}
          </button>
        ))}
```

with

```tsx
  const roots = useAppStore((s) => s.snapshot?.nodes.filter((n) => n.parents.length === 0).map((n) => n.name) ?? []);
  const download = async (format: "py" | "ipynb") => {
    const { result } = await rpc.request<{ text: string }>("session.export", { format });
    const type = format === "py" ? "text/x-python" : "application/x-ipynb+json";
    const url = URL.createObjectURL(new Blob([result.text], { type }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${roots.join("_") || "framelab"}.${format}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };
```

`App.tsx`, inside the connection effect:

```ts
    // Keep what the UI shows in memory: open tables, the selection and open figures' sources.
    const offPins = store.subscribe((s, prev) => {
      if (s.tables === prev.tables && s.plots === prev.plots && s.selectedId === prev.selectedId && s.snapshot?.figures === prev.snapshot?.figures) return;
      const figures = (s.snapshot?.figures ?? []).filter((f) => s.plots.includes(f.id));
      const ids = new Set([...s.tables, ...(s.selectedId ? [s.selectedId] : []), ...figures.flatMap((f) => f.sources)]);
      void rpc.request("session.pins", { ids: [...ids] }).catch(() => undefined);
    });
```

(and call `offPins()` in the cleanup).

`OpForm.tsx`: keep `const [forceable, setForceable] = useState(false)`; set it to `true` when a preview or apply error is an `RpcError` whose code is `"too_big"` or `"string_aggregation"` (reset it when the values change); when `forceable`, show next to "Aplicar"

```tsx
          {forceable ? (
            <button type="button" className="fl-btn fl-btn-quiet-danger" disabled={!built.op || busy} onClick={() => void submit(true)}>
              {t("form.force")}
            </button>
          ) : null}
```

with `submit(force = false)` calling `applyOp(rpc, built.op, { force })`, and let "Aplicar" stay enabled when the only problem is a guard (`built.op` exists).

`app.css`:

```css
.fl-root .fl-canvas-tools { position: absolute; top: 10px; left: 10px; z-index: 5; display: flex; gap: 6px; }
.fl-root .fl-card[data-state="freed"] { opacity: .75; }
.fl-root .fl-card[data-state="cancelled"] { border-style: dashed; }
.fl-root .fl-hint-inline { font-size: 11.5px; }
```

i18n (`es` / `en`): `node.state.cancelled` "cancelado" / "cancelled"; `node.state.freed` "liberado (se recalcula al usarlo)" / "freed (recomputed when used)"; `node.cancelling` "cancelando…" / "cancelling…"; `menu.cancel` "Cancelar cálculo" / "Cancel"; `menu.retry` "Reintentar" / "Retry"; `menu.rename` "Renombrar…" / "Rename…"; `rename.title` "Renombrar {{name}}" / "Rename {{name}}"; `rename.help` "Es el nombre de la variable en el código; los nodos derivados con nombre automático lo siguen." / "It is the variable name in the code; derived nodes with automatic names follow it."; `rename.confirm` "Renombrar" / "Rename"; `workbench.undo` "Deshacer" / "Undo"; `workbench.redo` "Rehacer" / "Redo"; `workbench.clear_failed` "Quitar nodos con error" / "Remove failed nodes"; `code.export_title` "Toda la sesión:" / "Whole session:"; `form.force` "Aplicar de todos modos" / "Apply anyway"; `errors.too_big` "Resultado demasiado grande" / "Result too big"; `errors.string_aggregation` "Agregación sobre columnas de texto" / "Aggregation over text columns"; `errors.name_taken` "Ese nombre ya existe" / "That name already exists"; `errors.cannot_rename` "No se puede renombrar" / "Cannot rename"; `errors.cannot_edit` "No se puede editar" / "Cannot edit".

- [ ] **Step 4: Extend the workbench E2E** — at the end of `frontend/tests/e2e/workbench.e2e.mjs`, before the console-error check:

```js
// undo / redo from the keyboard on the workbench
await page.getByRole("button", { name: /← Workbench/ }).click();
await page.keyboard.press("Control+z");
await created.waitFor({ state: "detached", timeout: 5000 }).catch(() => fail("Ctrl+Z did not undo the new node"));
await page.keyboard.press("Control+y");
await created.waitFor({ timeout: 5000 }).catch(() => fail("Ctrl+Y did not redo the new node"));
```

- [ ] **Step 5: Build, lint and run the E2Es**

Run: `cd frontend && mise exec -- pnpm typecheck && mise exec -- pnpm lint && mise exec -- pnpm build && cd .. && .venv/bin/python -m pytest tests/test_workbench_e2e.py tests/test_plot_e2e.py -m slow -q`
Expected: no type or lint errors; both E2E tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "Workbench: undo/redo, cancel, retry, rename, clear failed nodes, session export, pins"
```

---

### Task 13: Close the milestone

**Files:**
- Modify: `docs/superpowers/specs/2026-09-23-framelab-design.md` (M1b "Entregado" note)

- [ ] **Step 1: Full verification**

Run: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q`
Expected: ruff clean; every test passes, slow ones included.

- [ ] **Step 2: Record what shipped** — under the M1b bullet of the spec add an **Entregado (fecha)** note listing: code styles (quotes, aliases, query with mask fallback, assign, chained) proven by fidelity tests; names root + last steps and rename with auto-following; history (create/delete/rename/edit-as-new) with undo/redo; cancel/retry/clear; guards (exact merge sizes, reshaping estimates, string aggregations) with force; result cache with freed nodes and pins; generated catalog (`catalog/pandas.json.gz`, `tools/gen_catalog.py`); export `.py`/`.ipynb`; autosave + `fl.open`/`fl.autosaves`. Pending for later milestones: preferences UI for the code styles (M7), catalog-driven forms (M2b/M4), "inline de intermedios perezosos" style (not planned).

- [ ] **Step 3: Commit and push**

```bash
git add docs/superpowers/specs/2026-09-23-framelab-design.md
git commit -m "Record what M1b shipped in the spec"
git push
```

Expected: CI green on the three operating systems; the `publish` job uploads a new `framelab` version once PyPI trusted publishing is configured.
