"""Session: the Python-side source of truth (M0: frozen roots + snapshot)."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..naming import RootSpec
from ..options import OptionsRegistry
from ..options import registry as default_registry
from ..protocol.schema import SessionSnapshot

__all__ = ["Session"]


@dataclass(frozen=True)
class _Root:
    id: str
    name: str
    obj: pd.DataFrame | pd.Series
    source_expr: str | None


class Session:
    """Everything a framelab UI shows; also what ``fl.explore()`` returns."""

    def __init__(self, roots: list[RootSpec], options: OptionsRegistry | None = None) -> None:
        self.id = secrets.token_hex(8)
        self.rev = 0
        self._options = options if options is not None else default_registry
        self._roots: dict[str, _Root] = {}
        for i, spec in enumerate(roots, start=1):
            if not isinstance(spec.obj, (pd.DataFrame, pd.Series)):
                raise TypeError(
                    "framelab.explore expects pandas DataFrame or Series objects; "
                    f"got {type(spec.obj).__name__} for {spec.name!r}"
                )
            # Copy-on-Write: a shallow copy freezes the root; later edits by the user
            # to their own variable never leak into the session (and cost no memory).
            frozen = spec.obj.copy(deep=False)
            self._roots[spec.name] = _Root(f"n{i}", spec.name, frozen, spec.source_expr)
        self.widget: Any = None

    @property
    def names(self) -> list[str]:
        return list(self._roots)

    def __getitem__(self, name: str) -> pd.DataFrame | pd.Series:
        return self._roots[name].obj

    def __contains__(self, name: object) -> bool:
        return name in self._roots

    def __len__(self) -> int:
        return len(self._roots)

    def __iter__(self) -> Iterator[str]:
        return iter(self._roots)

    def source_expr(self, name: str) -> str | None:
        return self._roots[name].source_expr

    def snapshot(self) -> SessionSnapshot:
        return {
            "rev": self.rev,
            "session_id": self.id,
            "roots": [
                {
                    "id": r.id,
                    "name": r.name,
                    "kind": "DataFrame" if isinstance(r.obj, pd.DataFrame) else "Series",
                    "shape": [int(n) for n in r.obj.shape],
                }
                for r in self._roots.values()
            ],
            "options": self._options.describe(),  # type: ignore[typeddict-item]
        }

    def __repr__(self) -> str:
        return f"<framelab.Session {self.id}: {', '.join(self.names)}>"
