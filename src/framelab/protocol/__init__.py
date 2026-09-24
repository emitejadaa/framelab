"""framelab wire protocol: envelopes, binary frames and shared schema."""

from .codec import ProtocolError, decode_frame, dumps, encode_frame, validate_envelope
from .messages import make_error, make_event, make_response
from .schema import PROTOCOL_VERSION

__all__ = [
    "PROTOCOL_VERSION",
    "ProtocolError",
    "decode_frame",
    "dumps",
    "encode_frame",
    "make_error",
    "make_event",
    "make_response",
    "validate_envelope",
]
