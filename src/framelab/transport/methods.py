"""Session methods exposed over the protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..ops import op_from_json

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

__all__ = ["register_session_methods"]


def register_session_methods(dispatcher: Dispatcher) -> None:
    from .dispatcher import Reply

    session = dispatcher.session

    def apply(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        node = session.apply(op_from_json(params.get("op")), name=params.get("name"))
        return {"node": node.info()}

    def summary(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        return session.summary(str(params.get("id")))

    def window(params: dict[str, Any], _buffers: list[bytes]) -> Reply:
        data, meta = session.window(
            str(params.get("id")),
            offset=int(params.get("offset", 0)),
            limit=min(int(params.get("limit", 200)), 5000),
            col_start=int(params.get("col_start", 0)),
            col_stop=params.get("col_stop"),
        )
        return Reply(meta, [data])

    def code(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        mode = params.get("mode", "origin")
        return {
            "code": session.code(str(params.get("id")), mode="step" if mode == "step" else "origin")
        }

    dispatcher.register("node.apply", apply)
    dispatcher.register("node.summary", summary)
    dispatcher.register("node.window", window)
    dispatcher.register("node.code", code)
