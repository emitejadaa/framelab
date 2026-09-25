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
