"""Session methods exposed over the protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import BadRequest
from ..ops import op_from_json

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

__all__ = ["register_session_methods"]


def _int(params: dict[str, Any], key: str, default: int | None, *, minimum: int = 0) -> int | None:
    value = params.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BadRequest(f"{key} must be an integer >= {minimum}")
    return value


def _id(params: dict[str, Any]) -> str:
    value = params.get("id")
    if not isinstance(value, str) or not value:
        raise BadRequest("id must be a node id or name")
    return value


def register_session_methods(dispatcher: Dispatcher) -> None:
    from .dispatcher import Reply

    session = dispatcher.session

    def apply(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        node = session.apply(op_from_json(params.get("op")), name=params.get("name"))
        return {"node": node.info()}

    def summary(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        return session.summary(_id(params))

    def window(params: dict[str, Any], _buffers: list[bytes]) -> Reply:
        data, meta = session.window(
            _id(params),
            offset=_int(params, "offset", 0),
            limit=min(_int(params, "limit", 200), 5000),
            col_start=_int(params, "col_start", 0),
            col_stop=_int(params, "col_stop", None),
        )
        return Reply(meta, [data])

    def code(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        mode = params.get("mode", "origin")
        return {"code": session.code(_id(params), mode="step" if mode == "step" else "origin")}

    def preview(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        return session.preview(op_from_json(params.get("op")), name=params.get("name"))

    dispatcher.register("node.apply", apply)
    dispatcher.register("op.preview", preview)
    dispatcher.register("node.summary", summary)
    dispatcher.register("node.window", window)
    dispatcher.register("node.code", code)
