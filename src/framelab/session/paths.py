"""Where framelab writes files the user asks for: relative paths are relative to the folder
Python runs in, exactly like the code framelab shows would write them."""

from __future__ import annotations

from pathlib import Path

from ..errors import BadRequest

__all__ = ["output_path"]


def output_path(path: object, suffixes: tuple[str, ...]) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise BadRequest("path must be a file name")
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    if target.suffix.lower() not in suffixes:
        raise BadRequest(f"the file name must end in {suffixes[0]}")
    if target.is_dir() or not target.parent.is_dir():
        raise BadRequest(f"cannot write {target}: the folder does not exist")
    return target
