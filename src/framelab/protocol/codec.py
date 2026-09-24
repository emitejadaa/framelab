"""Frames: JSON text, or binary = uint32 BE header length + JSON header + raw buffers."""

from __future__ import annotations

import json
import struct
from collections.abc import Iterable
from typing import Any

import numpy as np

from .schema import PROTOCOL_VERSION, Envelope

__all__ = ["ProtocolError", "decode_frame", "dumps", "encode_frame", "validate_envelope"]

_HEADER = struct.Struct(">I")
_VALID_TYPES = frozenset({"req", "res", "evt", "cancel"})


class ProtocolError(ValueError):
    """A frame or envelope does not follow the framelab protocol."""


def _default(obj: Any) -> Any:
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    raise TypeError(f"{type(obj).__name__} is not JSON serializable")


def dumps(obj: Any) -> str:
    return json.dumps(
        obj, default=_default, allow_nan=False, ensure_ascii=False, separators=(",", ":")
    )


def validate_envelope(obj: Any) -> Envelope:
    if not isinstance(obj, dict):
        raise ProtocolError("envelope must be a JSON object")
    if obj.get("v") != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version {obj.get('v')!r}")
    kind = obj.get("type")
    if kind not in _VALID_TYPES:
        raise ProtocolError(f"invalid message type {kind!r}")
    if kind in ("req", "evt") and not isinstance(obj.get("method"), str):
        raise ProtocolError(f"{kind} message without method")
    if kind in ("req", "res", "cancel") and not isinstance(obj.get("id"), str):
        raise ProtocolError(f"{kind} message without id")
    return obj  # type: ignore[return-value]


def encode_frame(envelope: Envelope | dict[str, Any], buffers: Iterable[bytes] = ()) -> bytes | str:
    bufs = [bytes(b) for b in buffers]
    if not bufs:
        return dumps(envelope)
    header = dumps({**envelope, "buffers": [len(b) for b in bufs]}).encode("utf-8")
    return b"".join([_HEADER.pack(len(header)), header, *bufs])


def decode_frame(data: bytes | str) -> tuple[Envelope, list[bytes]]:
    if isinstance(data, str):
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid JSON: {exc}") from None
        return validate_envelope(obj), []
    if len(data) < _HEADER.size:
        raise ProtocolError("frame too short")
    (n,) = _HEADER.unpack_from(data, 0)
    end = _HEADER.size + n
    if end > len(data):
        raise ProtocolError("truncated header")
    try:
        obj = json.loads(data[_HEADER.size : end])
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError(f"invalid JSON header: {exc}") from None
    env = validate_envelope(obj)
    lengths = env.get("buffers", [])
    if not isinstance(lengths, list) or not all(isinstance(x, int) and x >= 0 for x in lengths):
        raise ProtocolError("invalid buffer lengths")
    out: list[bytes] = []
    offset = end
    for length in lengths:
        out.append(bytes(data[offset : offset + length]))
        offset += length
    if offset != len(data):
        raise ProtocolError("buffer lengths do not match the frame size")
    return env, out
