"""Open the framelab UI in the best available window, blocking until it closes."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

from .browser import open_in_browser
from .browsers import find_chromium
from .chromium import launch_app_window
from .webview import pywebview_available, run_pywebview

__all__ = ["default_order", "open_window"]


def default_order(platform: str | None = None) -> tuple[str, ...]:
    platform = platform or sys.platform
    if platform.startswith("linux"):
        return ("chromium", "pywebview", "browser")
    return ("pywebview", "chromium", "browser")


def open_window(server: Any, *, title: str = "framelab", order: Sequence[str] | None = None) -> str:
    """Show the UI served by ``server``; return the method used once the window closes."""
    errors: list[str] = []
    for method in order or default_order():
        try:
            if method == "chromium":
                browser = find_chromium()
                if browser is None:
                    continue
                redirect = server.write_redirect_file()
                try:
                    launch_app_window(browser, redirect.as_uri()).wait()
                finally:
                    redirect.unlink(missing_ok=True)
                if not server.ever_connected.is_set():
                    raise RuntimeError(f"{browser} exited before loading framelab")
                return "chromium"
            if method == "pywebview":
                if not pywebview_available():
                    continue
                run_pywebview(server.login_url, title)
                return "pywebview"
            if method == "browser":
                open_in_browser(server)
                return "browser"
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            errors.append(f"{method}: {exc}")
    raise RuntimeError(
        "framelab could not open a window (" + "; ".join(errors or ["no method available"]) + ")"
    )
