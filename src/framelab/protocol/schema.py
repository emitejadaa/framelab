"""Wire-level types shared by Python and the frontend (TypeScript is generated from here)."""

from typing import Any, Literal, NotRequired, TypedDict

PROTOCOL_VERSION = 1

MessageType = Literal["req", "res", "evt", "cancel"]
RootKind = Literal["DataFrame", "Series"]


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


class RootSummary(TypedDict):
    id: str
    name: str
    kind: RootKind
    shape: list[int]


class OptionDescription(TypedDict):
    key: str
    category: str
    value: Any
    default: Any
    type: str
    i18n_key: str
    choices: NotRequired[list[Any]]


class SessionSnapshot(TypedDict):
    rev: int
    session_id: str
    roots: list[RootSummary]
    options: list[OptionDescription]
