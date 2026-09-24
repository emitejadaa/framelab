import json

import numpy as np
import pytest

from framelab.protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    decode_frame,
    dumps,
    encode_frame,
    make_error,
    make_event,
    make_response,
)


def req(**extra):
    return {"v": PROTOCOL_VERSION, "id": "c1", "type": "req", "method": "app.ping", **extra}


def test_text_roundtrip():
    frame = encode_frame(req(params={"a": 1}))
    assert isinstance(frame, str)
    env, bufs = decode_frame(frame)
    assert env["params"] == {"a": 1}
    assert bufs == []


def test_binary_roundtrip_with_buffers():
    frame = encode_frame(req(), [b"abc", b"", bytes(range(10))])
    assert isinstance(frame, bytes)
    env, bufs = decode_frame(frame)
    assert bufs == [b"abc", b"", bytes(range(10))]
    assert env["buffers"] == [3, 0, 10]


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        json.dumps([1, 2]),
        json.dumps({"v": 99, "id": "x", "type": "req", "method": "m"}),
        json.dumps({"v": PROTOCOL_VERSION, "id": "x", "type": "nope"}),
        json.dumps({"v": PROTOCOL_VERSION, "id": "x", "type": "req"}),
        json.dumps({"v": PROTOCOL_VERSION, "type": "res"}),
        b"\x00\x00",
        b"\x00\x00\x00\x09{}",
    ],
)
def test_rejects_bad_frames(bad):
    with pytest.raises(ProtocolError):
        decode_frame(bad)


def test_rejects_mismatched_buffer_lengths():
    frame = encode_frame(req(), [b"abcd"])
    with pytest.raises(ProtocolError):
        decode_frame(frame[:-1])
    with pytest.raises(ProtocolError):
        decode_frame(frame + b"x")


def test_dumps_numpy_scalars_and_rejects_nan():
    out = json.loads(dumps({"a": np.int64(3), "b": np.float32(1.5), "c": np.bool_(True)}))
    assert out == {"a": 3, "b": 1.5, "c": True}
    with pytest.raises(ValueError):
        dumps({"x": float("nan")})


def test_message_builders():
    assert make_response("c1", {"ok": 1}) == {
        "v": PROTOCOL_VERSION,
        "id": "c1",
        "type": "res",
        "result": {"ok": 1},
    }
    err = make_error("c2", "internal", "boom", "Traceback...")
    assert err["error"] == {
        "code": "internal",
        "i18n_key": "errors.internal",
        "message": "boom",
        "traceback": "Traceback...",
    }
    assert "traceback" not in make_error("c3", "bad_request", "x")["error"]
    evt = make_event("node.state", {"id": "n1"}, rev=4)
    assert evt == {
        "v": PROTOCOL_VERSION,
        "type": "evt",
        "method": "node.state",
        "params": {"id": "n1"},
        "rev": 4,
    }
