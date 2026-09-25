"""The ``.framelab`` session document: ops and sources, never code or data."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from .. import __version__
from ..codegen.literals import label_text
from ..errors import FramelabError
from ..naming import RootSpec
from ..ops import op_from_json, op_to_json
from ..options import OptionsRegistry
from .core import Session

__all__ = [
    "FORMAT",
    "FORMAT_VERSION",
    "MIGRATIONS",
    "DocumentError",
    "from_document",
    "load",
    "save",
    "schema_hash",
    "to_document",
]

FORMAT = "framelab"
FORMAT_VERSION = 1
# from_version -> function upgrading a document to from_version + 1
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class DocumentError(FramelabError, ValueError):
    code = "bad_document"


def schema_hash(obj: pd.DataFrame | pd.Series) -> str:
    frame = obj.to_frame() if isinstance(obj, pd.Series) else obj
    parts = [[label_text(label), str(dtype)] for label, dtype in frame.dtypes.items()]
    return hashlib.sha256(json.dumps([type(obj).__name__, parts]).encode()).hexdigest()[:16]


def to_document(session: Session) -> dict[str, Any]:
    nodes = []
    for node in session.nodes():
        entry: dict[str, Any] = {"id": node.id, "name": node.name, "name_auto": node.name_auto}
        if node.is_root:
            value = session.wait(node.id)
            entry["source"] = {
                "kind": "memory",
                "var": node.name,
                "source_expr": node.source_expr,
                "shape": list(node.shape or ()),
                "schema_hash": schema_hash(value),
            }
        else:
            entry["op"] = op_to_json(node.op)  # type: ignore[arg-type]
        nodes.append(entry)
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "framelab_version": __version__,
        "pandas_version": pd.__version__,
        "graph": {"version": 1, "nodes": nodes},
        "figures": {"version": 1, "items": session.plots.to_json()},
    }


def save(session: Session, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(to_document(session), ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _migrate(doc: dict[str, Any]) -> dict[str, Any]:
    version = doc.get("format_version")
    if not isinstance(version, int):
        raise DocumentError("the document has no format_version")
    if version > FORMAT_VERSION:
        raise DocumentError(
            f"this file was written by a newer framelab (format {version}); please upgrade framelab"
        )
    while version < FORMAT_VERSION:
        doc = MIGRATIONS[version](doc)
        version = doc["format_version"]
    return doc


def load(path: str | Path) -> dict[str, Any]:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentError(f"cannot read {path}: {exc}") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise DocumentError(f"{path} is not a framelab document")
    return _migrate(doc)


def from_document(
    doc: dict[str, Any],
    roots: Mapping[str, pd.DataFrame | pd.Series],
    options: OptionsRegistry | None = None,
) -> tuple[Session, list[str]]:
    doc = _migrate(doc)
    entries = doc["graph"]["nodes"]
    root_entries = [e for e in entries if "source" in e]
    missing = [e["name"] for e in root_entries if e["name"] not in roots]
    if missing:
        raise DocumentError(f"missing data for: {', '.join(missing)}")
    warnings: list[str] = []
    specs = []
    for entry in root_entries:
        obj = roots[entry["name"]]
        if schema_hash(obj) != entry["source"]["schema_hash"]:
            warnings.append(f"{entry['name']}: columns or dtypes changed since the file was saved")
        specs.append(RootSpec(entry["name"], obj, entry["source"].get("source_expr")))
    session = Session(specs, options)
    expected = [e["id"] for e in root_entries]
    actual = [n.id for n in session.nodes()]
    if expected != actual:
        raise DocumentError("root ids in the document are not n1..nK in order")
    for entry in entries:
        if "source" in entry:
            continue
        session.apply(
            op_from_json(entry["op"]),
            name=None if entry.get("name_auto", True) else entry["name"],
            node_id=entry["id"],
        )
        if entry.get("name_auto", True) and session.node(entry["id"]).name != entry["name"]:
            warnings.append(f"{entry['name']} was renamed to {session.node(entry['id']).name}")
    for item in (doc.get("figures") or {}).get("items", []):
        try:
            session.plots.restore(item["id"], item["spec"], item.get("exported"))
        except (FramelabError, KeyError, TypeError) as exc:
            warnings.append(f"figure {item.get('id')!r} could not be restored: {exc}")
    return session, warnings
