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

__all__ = ["autosaves", "explore", "last_session", "open"]

_last_session: Session | None = None


def _static_dir() -> Path:
    return require_static()


def _open_window(server: Any, *, title: str) -> str:
    from .launch import open_window

    return open_window(server, title=title)


def _display(obj: Any) -> None:
    from IPython.display import display

    display(obj)


def _start_autosave(session: Session) -> None:
    if registry.get("general.autosave"):
        from .session.autosave import Autosaver

        session.autosaver = Autosaver(session)


def _show(session: Session, mode: str | None) -> Session:
    """Display a session: inline in notebooks, a window (blocking) from scripts."""
    global _last_session
    env = detect_env()
    resolved = resolve_mode(mode or registry.get("general.open_mode"), env)
    if resolved == "window" and env in INLINE_ENVS:
        warnings.warn(
            "opening a separate window from a notebook arrives in a later version; "
            "showing the workbench inline",
            stacklevel=3,
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

        roots = [n.name for n in session.nodes() if n.is_root]
        title = f"framelab · {', '.join(roots)}"
        server = FramelabServer(dispatcher, _static_dir(), title=title)
        server.start()
        try:
            _open_window(server, title=title)
        finally:
            server.stop()
            if session.autosaver is not None:
                session.autosaver.flush()
    return session


def explore(*dfs: Any, name: str | None = None, mode: str | None = None, **named: Any) -> Session:
    """Open the framelab workbench for one or more DataFrames or Series.

    In a script it opens a window and blocks until it is closed (like ``plt.show()``);
    in Jupyter / VS Code / Colab it shows the workbench inline and returns at once.
    Either way it returns the :class:`Session`. Sessions are autosaved (``fl.open("last")``).
    """
    if not dfs and not named:
        raise TypeError("explore() needs at least one DataFrame or Series")
    frame = user_frame(sys._getframe(1))
    try:
        specs = resolve_root_names(dfs, named, frame, explicit_name=name, callee=explore)
    finally:
        del frame
    session = Session(specs, registry)
    _start_autosave(session)
    return _show(session, mode)


def open(path: str | Path = "last", *, mode: str | None = None, **roots: Any) -> Session:  # noqa: A001
    """Reopen a saved or autosaved session with its data: ``fl.open("last", ventas=df)``."""
    from .session.autosave import latest
    from .session.document import from_document, load

    target = latest() if path == "last" else Path(path)
    session, problems = from_document(load(target), roots, registry)
    for message in problems:
        warnings.warn(message, stacklevel=2)
    _start_autosave(session)
    return _show(session, mode)


def autosaves() -> list[dict[str, Any]]:
    """Recently saved sessions, newest first (path, time, data names, sizes)."""
    from .session.autosave import recent

    return recent()


def last_session() -> Session | None:
    """The session returned by the most recent ``explore()`` call."""
    return _last_session
