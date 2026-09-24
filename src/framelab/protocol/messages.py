"""Constructors for the envelopes the Python side sends."""

from __future__ import annotations

from typing import Any

from .schema import PROTOCOL_VERSION, Envelope


def make_response(msg_id: str, result: Any) -> Envelope:
    return {"v": PROTOCOL_VERSION, "id": msg_id, "type": "res", "result": result}


def make_error(msg_id: str, code: str, message: str, traceback: str | None = None) -> Envelope:
    error: dict[str, Any] = {"code": code, "i18n_key": f"errors.{code}", "message": message}
    if traceback is not None:
        error["traceback"] = traceback
    return {"v": PROTOCOL_VERSION, "id": msg_id, "type": "res", "error": error}  # type: ignore[typeddict-item]


def make_event(method: str, params: dict[str, Any], rev: int | None = None) -> Envelope:
    env: Envelope = {"v": PROTOCOL_VERSION, "type": "evt", "method": method, "params": params}
    if rev is not None:
        env["rev"] = rev
    return env
