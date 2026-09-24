"""Detect where framelab runs and decide whether the UI is shown inline or in a window."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal

__all__ = ["INLINE_ENVS", "Env", "Mode", "detect_env", "resolve_mode"]

Mode = Literal["inline", "window"]
_MISSING: Any = object()


class Env(StrEnum):
    SCRIPT = "script"
    REPL = "repl"
    IPYTHON_TERMINAL = "ipython-terminal"
    JUPYTER = "jupyter"
    VSCODE = "vscode"
    COLAB = "colab"
    MARIMO = "marimo"
    NO_WIDGETS = "no-widgets"


INLINE_ENVS = frozenset({Env.JUPYTER, Env.VSCODE, Env.COLAB, Env.MARIMO})


def _current_ipython(modules: Mapping[str, Any]) -> Any:
    ipy = modules.get("IPython")
    if ipy is None:
        return None
    try:
        return ipy.get_ipython()
    except Exception:
        return None


def _marimo_running(modules: Mapping[str, Any]) -> bool:
    mo = modules.get("marimo")
    if mo is None:
        return False
    try:
        return bool(mo.running_in_notebook())
    except Exception:
        return False


def detect_env(
    *,
    modules: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    ipython: Any = _MISSING,
    interactive: bool | None = None,
) -> Env:
    modules = sys.modules if modules is None else modules
    environ = os.environ if environ is None else environ
    if _marimo_running(modules):
        return Env.MARIMO
    shell = _current_ipython(modules) if ipython is _MISSING else ipython
    if shell is not None:
        name = type(shell).__name__
        if "google.colab" in modules:
            return Env.COLAB
        if "spyder_kernels" in modules or "PYCHARM_HOSTED" in environ:
            return Env.NO_WIDGETS
        if name == "ZMQInteractiveShell":
            return Env.VSCODE if "VSCODE_PID" in environ else Env.JUPYTER
        if name == "TerminalInteractiveShell":
            return Env.IPYTHON_TERMINAL
        return Env.NO_WIDGETS
    if interactive is None:
        interactive = hasattr(sys, "ps1") or bool(sys.flags.interactive)
    return Env.REPL if interactive else Env.SCRIPT


def resolve_mode(requested: str, env: Env) -> Mode:
    if requested == "auto":
        return "inline" if env in INLINE_ENVS else "window"
    if requested == "inline":
        if env not in INLINE_ENVS:
            raise ValueError(
                "mode='inline' needs Jupyter, VS Code, Colab or marimo; use mode='window' here"
            )
        return "inline"
    if requested == "window":
        return "window"
    raise ValueError(f"mode must be 'auto', 'inline' or 'window', not {requested!r}")
