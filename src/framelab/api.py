"""Public entry point: ``fl.explore()``."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any

from ._paths import require_static
from .env import INLINE_ENVS, detect_env, resolve_mode
from .naming import resolve_root_names, user_frame
from .options import registry
from .session import Session
from .transport.dispatcher import Dispatcher

__all__ = ["explore", "last_session"]

_last_session: Session | None = None


def _static_dir() -> Path:
    return require_static()


def _open_window(server: Any, *, title: str) -> str:
    from .launch import open_window

    return open_window(server, title=title)


def _display(obj: Any) -> None:
    from IPython.display import display

    display(obj)


def explore(*dfs: Any, name: str | None = None, mode: str | None = None, **named: Any) -> Session:
    """Open the framelab workbench for one or more DataFrames or Series.

    In a script it opens a window and blocks until it is closed (like ``plt.show()``);
    in Jupyter / VS Code / Colab it shows the workbench inline and returns at once.
    Either way it returns the :class:`Session`.
    """
    global _last_session
    if not dfs and not named:
        raise TypeError("explore() needs at least one DataFrame or Series")
    frame = user_frame(sys._getframe(1))
    try:
        specs = resolve_root_names(dfs, named, frame, explicit_name=name, callee=explore)
    finally:
        del frame
    session = Session(specs, registry)
    env = detect_env()
    resolved = resolve_mode(mode or registry.get("general.open_mode"), env)
    if resolved == "window" and env in INLINE_ENVS:
        warnings.warn(
            "opening a separate window from a notebook arrives in a later version; "
            "showing the workbench inline",
            stacklevel=2,
        )
        resolved = "inline"
    dispatcher = Dispatcher(session)
    _last_session = session
    if resolved == "inline":
        from .transport.widget import FramelabWidget

        widget = FramelabWidget(dispatcher, height=registry.get("general.inline_height"))
        session.widget = widget
        _display(widget)
    else:
        from .transport.server import FramelabServer

        title = f"framelab · {', '.join(session.names)}"
        server = FramelabServer(dispatcher, _static_dir(), title=title)
        server.start()
        try:
            _open_window(server, title=title)
        finally:
            server.stop()
    return session


def last_session() -> Session | None:
    """The session returned by the most recent ``explore()`` call."""
    return _last_session
