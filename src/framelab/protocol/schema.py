"""Wire-level types shared by Python and the frontend (TypeScript is generated from here)."""

from typing import Any, Literal, NotRequired, TypedDict

PROTOCOL_VERSION = 1

MessageType = Literal["req", "res", "evt", "cancel"]


class ErrorInfo(TypedDict):
    code: str
    i18n_key: str
    message: str
    traceback: NotRequired[str]


class Envelope(TypedDict):
    v: int
    type: MessageType
    id: NotRequired[str]
    method: NotRequired[str]
    params: NotRequired[dict[str, Any]]
    result: NotRequired[Any]
    error: NotRequired[ErrorInfo]
    buffers: NotRequired[list[int]]
    rev: NotRequired[int]


class HelloParams(TypedDict):
    protocol_version: int
    client: str


class HelloResult(TypedDict):
    protocol_version: int
    framelab_version: str
    session_id: str


class OptionDescription(TypedDict):
    key: str
    category: str
    value: Any
    default: Any
    type: str
    i18n_key: str
    choices: NotRequired[list[Any]]


NodeKindName = Literal["Unknown", "DataFrame", "Series", "GroupBy", "Index", "Value"]
NodeStateName = Literal["pending", "computing", "ready", "error", "blocked"]


class NodeErrorInfo(TypedDict):
    type: str
    message: str


class NodeInfo(TypedDict):
    id: str
    name: str
    kind: NodeKindName
    state: NodeStateName
    parents: list[str]
    label: str
    name_auto: bool
    shape: NotRequired[list[int]]
    error: NotRequired[NodeErrorInfo]
    warnings: NotRequired[list[str]]


class SessionSnapshot(TypedDict):
    rev: int
    session_id: str
    nodes: list[NodeInfo]
    options: list[OptionDescription]
