"""Nodes of the session graph."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import pandas as pd

from ..errors import FramelabError
from ..ops import Op
from ..protocol.schema import NodeInfo

__all__ = [
    "ErrorDetail",
    "Node",
    "NodeError",
    "NodeKind",
    "NodeState",
    "NotReady",
    "UnknownNode",
    "classify",
]


class NodeState(StrEnum):
    PENDING = "pending"
    COMPUTING = "computing"
    READY = "ready"
    ERROR = "error"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FREED = "freed"  # result released from memory; recomputed when used


class NodeKind(StrEnum):
    UNKNOWN = "Unknown"
    DATAFRAME = "DataFrame"
    SERIES = "Series"
    GROUPBY = "GroupBy"
    INDEX = "Index"
    VALUE = "Value"


@dataclass(frozen=True)
class ErrorDetail:
    type: str
    message: str
    traceback: str = ""


@dataclass
class Node:
    id: str
    name: str
    op: Op | None
    parents: tuple[str, ...] = ()
    name_auto: bool = True
    source_expr: str | None = None
    label: str = ""
    state: NodeState = NodeState.PENDING
    kind: NodeKind = NodeKind.UNKNOWN
    shape: tuple[int, ...] | None = None
    error: ErrorDetail | None = None
    warnings: tuple[str, ...] = ()
    alias: str = ""  # the word this node's op adds to automatic names
    force: bool = False  # created with the guards skipped
    cancel_requested: bool = False

    @property
    def is_root(self) -> bool:
        return self.op is None

    def info(self) -> NodeInfo:
        out: NodeInfo = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "state": self.state.value,
            "parents": list(self.parents),
            "label": self.label,
            "name_auto": self.name_auto,
        }
        if self.shape is not None:
            out["shape"] = list(self.shape)
        if self.error is not None:
            out["error"] = {"type": self.error.type, "message": self.error.message}
        if self.warnings:
            out["warnings"] = list(self.warnings)
        if self.cancel_requested and self.state in (NodeState.PENDING, NodeState.COMPUTING):
            out["cancelling"] = True
        return out


def classify(value: Any) -> tuple[NodeKind, tuple[int, ...] | None]:
    from pandas.api.typing import DataFrameGroupBy, SeriesGroupBy

    if isinstance(value, pd.DataFrame):
        return NodeKind.DATAFRAME, tuple(int(n) for n in value.shape)
    if isinstance(value, pd.Series):
        return NodeKind.SERIES, (int(len(value)),)
    if isinstance(value, (DataFrameGroupBy, SeriesGroupBy)):
        return NodeKind.GROUPBY, None
    if isinstance(value, pd.Index):
        return NodeKind.INDEX, (int(len(value)),)
    return NodeKind.VALUE, None


class NodeError(FramelabError):
    code = "node_error"

    def __init__(self, node: Node) -> None:
        self.node = node
        if node.error is not None:
            detail = f"{node.error.type}: {node.error.message}"
        elif node.state is NodeState.CANCELLED:
            detail = "was cancelled"
        else:
            detail = f"is {node.state.value} because an ancestor failed"
        super().__init__(
            f"{node.name} {detail}" if node.error is None else f"{node.name}: {detail}"
        )


class UnknownNode(FramelabError, KeyError):
    code = "unknown_node"


class NotReady(FramelabError, TimeoutError):
    code = "not_ready"
