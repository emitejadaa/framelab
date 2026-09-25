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
