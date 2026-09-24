"""Optional native window through pywebview (``pip install 'framelab[desktop]'``)."""

from __future__ import annotations

import importlib.util
import os
import sys
import threading


def pywebview_available() -> bool:
    return importlib.util.find_spec("webview") is not None


def _has_nvidia() -> bool:
    return os.path.exists("/proc/driver/nvidia/version")


def run_pywebview(url: str, title: str, width: int = 1400, height: int = 900) -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("pywebview must run on the main thread")
    if sys.platform.startswith("linux") and _has_nvidia():
        # WebKitGTK renders blank windows on NVIDIA's DMA-BUF path.
        os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
    import webview

    webview.create_window(title, url, width=width, height=height)
    webview.start()
