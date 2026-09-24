"""Last resort: a normal browser tab; the session ends once no tab stays connected."""

from __future__ import annotations

import time
import webbrowser
from collections.abc import Callable
from typing import Any


def open_in_browser(
    server: Any,
    *,
    first_connect_timeout: float = 120.0,
    grace: float = 60.0,
    poll: float = 0.25,
    opener: Callable[[str], Any] = webbrowser.open,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    redirect = server.write_redirect_file()
    try:
        opener(redirect.as_uri())
        start = time.monotonic()
        while not server.ever_connected.is_set():
            if time.monotonic() - start > first_connect_timeout:
                raise TimeoutError("the browser never connected to framelab")
            sleep(poll)
    finally:
        # The file carries the token; once the browser is in (or gave up) it must go.
        redirect.unlink(missing_ok=True)
    while server.idle_for() < grace:
        sleep(poll)
