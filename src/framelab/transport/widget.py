"""anywidget adapter: the same frontend bundle rendered inside notebook outputs."""

from __future__ import annotations

from typing import Any

import anywidget
import traitlets

from .._paths import require_static
from ..protocol import ProtocolError, make_error, validate_envelope
from .dispatcher import Dispatcher

_STATIC = require_static()


class FramelabWidget(anywidget.AnyWidget):
    _esm = _STATIC / "framelab.js"
    _css = _STATIC / "framelab.css"
    height = traitlets.Int(720).tag(sync=True)

    def __init__(self, dispatcher: Dispatcher, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._dispatcher = dispatcher
        self.on_msg(self._on_msg)
        self._remove_client = dispatcher.add_client(self._send_envelope)

    def _send_envelope(self, env: Any, buffers: list[bytes]) -> None:
        self.send(env, buffers=list(buffers) or None)

    def _on_msg(self, _widget: Any, content: Any, buffers: list[Any]) -> None:
        try:
            env = validate_envelope(content)
        except ProtocolError as exc:
            self._send_envelope(make_error("", "bad_request", str(exc)), [])
            return
        reply = self._dispatcher.handle(env, [bytes(b) for b in buffers])
        if reply is not None:
            self._send_envelope(*reply)

    def close(self) -> None:
        self._remove_client()
        super().close()
