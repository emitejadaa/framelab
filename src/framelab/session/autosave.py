"""Autosave: the session document is written in the background a moment after each change.

Documents hold ops, names and figure specs, never data; ``fl.open("last", ventas=df)`` brings a
session back with the data passed again. A failing save is logged and never interrupts work.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import platformdirs

from .document import to_document

__all__ = ["Autosaver", "default_directory", "latest", "recent"]

log = logging.getLogger("framelab")
KEEP = 20


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:  # deleted meanwhile (another session pruned it)
        return 0.0


def default_directory() -> Path:
    override = os.environ.get("FRAMELAB_DATA_DIR")
    base = Path(override) if override else Path(platformdirs.user_data_dir("framelab"))
    return base / "sessions"


class Autosaver:
    def __init__(
        self,
        session: Any,
        directory: Path | str | None = None,
        *,
        delay: float = 2.0,
        keep: int = KEEP,
    ) -> None:
        self.session = session
        self.directory = Path(directory) if directory is not None else default_directory()
        self.delay = delay
        self.keep = keep
        self.path = self.directory / f"{time.strftime('%Y%m%d-%H%M%S')}-{session.id}.framelab"
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._dirty = False
        self._unsubscribe = session.subscribe(self._changed)

    def _changed(self, method: str, _params: dict[str, Any]) -> None:
        if not method.startswith(("node.", "figure.", "graph.")):
            return
        with self._lock:
            self._dirty = True
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.delay, self.save)
            self._timer.daemon = True
            self._timer.start()

    def save(self) -> Path | None:
        with self._lock:
            self._dirty = False
            self._timer = None
        try:
            document = to_document(self.session)
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, self.path)
            self._prune()
        except Exception:
            log.warning("framelab: autosave failed", exc_info=True)
            return None
        return self.path

    def _prune(self) -> None:
        files = sorted(
            self.directory.glob("*.framelab"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        for old in files[self.keep :]:
            if old != self.path:
                with contextlib.suppress(OSError):
                    old.unlink()

    def flush(self) -> None:
        """Save now if something changed since the last save."""
        with self._lock:
            pending = self._dirty
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if pending:
            self.save()

    def close(self) -> None:
        self._unsubscribe()
        self.flush()


def recent(directory: Path | str | None = None) -> list[dict[str, Any]]:
    """Saved sessions, newest first."""
    folder = Path(directory) if directory is not None else default_directory()
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.framelab"), key=_mtime, reverse=True):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            nodes = document["graph"]["nodes"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        out.append(
            {
                "path": str(path),
                "saved": path.stat().st_mtime,
                "roots": [e["name"] for e in nodes if "source" in e],
                "nodes": len(nodes),
                "figures": len((document.get("figures") or {}).get("items", [])),
            }
        )
    return out


def latest(directory: Path | str | None = None) -> Path:
    items = recent(directory)
    if not items:
        raise FileNotFoundError("there is no saved framelab session yet")
    return Path(items[0]["path"])
