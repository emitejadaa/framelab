"""Locate an installed Chromium-family browser (Chrome, Chromium, Edge, Brave)."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable

LINUX_NAMES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "microsoft-edge",
    "microsoft-edge-stable",
    "brave-browser",
    "brave",
)
MAC_APPS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)
WIN_EXES = ("chrome.exe", "msedge.exe", "brave.exe")
WIN_RELATIVE = (
    r"Google\Chrome\Application\chrome.exe",
    r"Microsoft\Edge\Application\msedge.exe",
    r"BraveSoftware\Brave-Browser\Application\brave.exe",
)


def _windows_candidates(exists: Callable[[str], bool]) -> str | None:
    try:
        import winreg
    except ImportError:
        return None
    for exe in WIN_EXES:
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
            try:
                with winreg.OpenKey(hive, key) as handle:
                    value, _ = winreg.QueryValueEx(handle, None)
            except OSError:
                continue
            if value and exists(value):
                return value
    for env_var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env_var)
        if not base:
            continue
        for rel in WIN_RELATIVE:
            candidate = os.path.join(base, rel)
            if exists(candidate):
                return candidate
    return None


def find_chromium(
    *,
    platform: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
    exists: Callable[[str], bool] = os.path.exists,
) -> str | None:
    """Path of a Chromium-family browser, or None. ``FRAMELAB_BROWSER`` overrides."""
    override = os.environ.get("FRAMELAB_BROWSER")
    if override:
        return override if exists(override) else which(override)
    platform = platform or sys.platform
    if platform.startswith(("linux", "freebsd")):
        for name in LINUX_NAMES:
            path = which(name)
            if path:
                return path
        return None
    if platform == "darwin":
        return next((p for p in MAC_APPS if exists(p)), None)
    if platform == "win32":
        return _windows_candidates(exists) or which("msedge") or which("chrome")
    return None
