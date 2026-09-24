"""Transport-agnostic request handling and event fan-out."""

from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .. import __version__
from ..errors import FramelabError
from ..protocol import PROTOCOL_VERSION, make_error, make_event, make_response
from ..protocol.schema import Envelope
from ..session import Session

__all__ = ["Dispatcher", "ProtocolMismatch", "Reply"]

log = logging.getLogger("framelab")

Handler = Callable[[dict[str, Any], list[bytes]], Any]
Send = Callable[[Envelope, list[bytes]], None]


class ProtocolMismatch(Exception):
    """Client and server speak different protocol versions."""


@dataclass
class Reply:
    """A handler result that also carries binary buffers."""

    result: Any
    buffers: list[bytes] = field(default_factory=list)


class Dispatcher:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._handlers: dict[str, Handler] = {}
        self._clients: dict[int, Send] = {}
        self._next_client = 0
        self._lock = threading.Lock()
        self.register("session.hello", self._hello)
        self.register("session.snapshot", lambda params, buffers: self.session.snapshot())
        self.register("app.ping", lambda params, buffers: {"pong": True})

        from .methods import register_session_methods

        register_session_methods(self)
        self._unsubscribe = session.subscribe(self.emit)

    def register(self, method: str, handler: Handler) -> None:
        if method in self._handlers:
            raise ValueError(f"handler for {method!r} already registered")
        self._handlers[method] = handler

    def handle(self, env: Envelope, buffers: list[bytes]) -> tuple[Envelope, list[bytes]] | None:
        kind = env["type"]
        msg_id = env.get("id", "")
        if kind == "cancel":
            return None
        if kind != "req":
            return make_error(msg_id, "bad_request", f"unexpected message type {kind!r}"), []
        method = env.get("method", "")
        handler = self._handlers.get(method)
        if handler is None:
            return make_error(msg_id, "unknown_method", f"unknown method {method!r}"), []
        try:
            out = handler(env.get("params", {}), buffers)
        except ProtocolMismatch as exc:
            return make_error(msg_id, "protocol_mismatch", str(exc)), []
        except FramelabError as exc:
            return make_error(msg_id, exc.code, str(exc)), []
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            return make_error(msg_id, "internal", message, traceback.format_exc()), []
        if isinstance(out, Reply):
            return make_response(msg_id, out.result), list(out.buffers)
        return make_response(msg_id, out), []

    def add_client(self, send: Send) -> Callable[[], None]:
        with self._lock:
            key = self._next_client
            self._next_client += 1
            self._clients[key] = send

        def remove() -> None:
            with self._lock:
                self._clients.pop(key, None)

        return remove

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def emit(
        self, method: str, params: dict[str, Any] | None = None, buffers: Iterable[bytes] = ()
    ) -> None:
        env = make_event(method, params or {}, rev=self.session.rev)
        payload = list(buffers)
        with self._lock:
            clients = list(self._clients.values())
        for send in clients:
            try:
                send(env, payload)
            except Exception:
                log.exception("framelab: failed to deliver %s to a client", method)

    def _hello(self, params: dict[str, Any], buffers: list[bytes]) -> dict[str, Any]:
        version = params.get("protocol_version")
        if version != PROTOCOL_VERSION:
            raise ProtocolMismatch(
                f"the UI speaks protocol {version!r} but Python speaks {PROTOCOL_VERSION}"
            )
        return {
            "protocol_version": PROTOCOL_VERSION,
            "framelab_version": __version__,
            "session_id": self.session.id,
        }
