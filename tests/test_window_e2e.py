"""E2E #1 — a real Chromium boots the real bundle through the token flow; close is detected."""

import os
import time

import pandas as pd
import pytest

from framelab._paths import require_static
from framelab.launch.browsers import find_chromium
from framelab.launch.chromium import launch_app_window
from framelab.naming import RootSpec
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher
from framelab.transport.server import FramelabServer

pytestmark = pytest.mark.slow


@pytest.mark.skipif(find_chromium() is None, reason="no Chromium-family browser installed")
def test_real_browser_boots_the_frontend_and_close_is_detected():
    ventas = pd.DataFrame({"a": range(1000), "b": 0, "c": 0, "d": 0, "e": 0})
    d = Dispatcher(Session([RootSpec("ventas", ventas, None)]))
    seen: list[str] = []
    original = d.handle

    def spy(env, bufs):
        seen.append(env.get("method", ""))
        return original(env, bufs)

    d.handle = spy
    server = FramelabServer(d, require_static())
    server.start()
    redirect = server.write_redirect_file()
    args = ["--headless=new", "--disable-gpu"]
    if os.environ.get("CI"):
        # Ubuntu 24.04 runners block the unprivileged user namespaces Chrome's sandbox needs.
        args.append("--no-sandbox")
    window = launch_app_window(find_chromium(), redirect.as_uri(), extra_args=args)
    try:
        deadline = time.monotonic() + 30
        while "session.snapshot" not in seen and time.monotonic() < deadline:
            time.sleep(0.05)
        assert "session.hello" in seen and "session.snapshot" in seen
        t0 = time.monotonic()
        window.close()
        window.wait(timeout=10)
        assert time.monotonic() - t0 < 5
    finally:
        window.close()
        redirect.unlink(missing_ok=True)
        server.stop()
