"""Figures: editable documents (with undo) that draw session nodes with matplotlib."""

from __future__ import annotations

import copy
import io
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..codegen.literals import emit_literal
from ..codegen.script import pipeline_lines, used_modules
from ..codegen.style import import_lines, restyle
from ..errors import BadRequest
from ..naming import unique_name
from ..plot.codegen import FigureCode, generate
from ..plot.fields import default_layer, fields, suggestions
from ..plot.kinds import KINDS, catalog
from ..plot.render import PREVIEW_ROWS, build, png_bytes, style_context
from ..plot.spec import FigureSpecError, normalize
from .node import NodeError, NotReady, UnknownNode

if TYPE_CHECKING:
    from matplotlib.figure import Figure

    from .core import Session

__all__ = ["FigureDoc", "FigureStore", "UnknownFigure"]

MAX_UNDO = 200


class UnknownFigure(BadRequest):
    code = "unknown_figure"


@dataclass
class FigureDoc:
    id: str
    spec: dict[str, Any]
    version: int = 1
    undo: list[dict[str, Any]] = field(default_factory=list)
    redo: list[dict[str, Any]] = field(default_factory=list)
    exported: dict[str, Any] | None = None
    origin: str | None = None  # the node the figure was created from (the gallery's default)

    def sources(self) -> list[str]:
        out: list[str] = []
        for axes in self.spec["axes"]:
            for layer in axes["layers"]:
                if layer["source"] not in out:
                    out.append(layer["source"])
        return out

    def info(self) -> dict[str, Any]:
        layers = [ly for axes in self.spec["axes"] for ly in axes["layers"]]
        return {
            "id": self.id,
            "name": self.spec["name"],
            "sources": self.sources(),
            "kinds": list(dict.fromkeys(ly["kind"] for ly in layers)),
            "nlayers": len(layers),
        }

    def state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "spec": copy.deepcopy(self.spec),  # callers may edit it and send it back
            "can_undo": bool(self.undo),
            "can_redo": bool(self.redo),
            "exported": self.exported,
            "origin": self.origin,
        }


class FigureStore:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._docs: dict[str, FigureDoc] = {}
        self._next = 1
        self._lock = threading.RLock()

    # ---- lookup ---------------------------------------------------------------------------------
    def _doc(self, fid: str) -> FigureDoc:
        doc = self._docs.get(fid)
        if doc is None:
            for d in self._docs.values():
                if d.spec["name"] == fid:
                    return d
            raise UnknownFigure(f"no figure called {fid!r}")
        return doc

    def infos(self) -> list[dict[str, Any]]:
        with self._lock:
            return [d.info() for d in self._docs.values()]

    def names(self) -> set[str]:
        with self._lock:
            return {d.spec["name"] for d in self._docs.values()}

    def ids(self) -> list[str]:
        with self._lock:
            return list(self._docs)

    def get(self, fid: str) -> dict[str, Any]:
        with self._lock:
            return self._doc(fid).state()

    def _taken(self, exclude: str | None = None) -> set[str]:
        names = set(self._session.names)
        names.update(d.spec["name"] for d in self._docs.values() if d.id != exclude)
        return names

    def _changed(self, doc: FigureDoc) -> dict[str, Any]:
        self._session.rev += 1
        self._session._emit("figure.changed", doc.info())
        return doc.state()

    # ---- editing --------------------------------------------------------------------------------
    def create(self, source: str | None = None, name: str | None = None) -> dict[str, Any]:
        base = "fig"
        if source is not None:
            node = self._session.node(source)
            source, base = node.id, f"fig_{node.name}"
        with self._lock:
            final = unique_name(name or base, self._taken())
            fid = f"f{self._next}"
            self._next += 1
            spec = normalize({"name": final}, set())
            doc = self._docs[fid] = FigureDoc(fid, spec, origin=source)
            state = self._changed(doc)
        state["suggestions"] = self.suggest(source) if source else []
        return state

    def restore(self, fid: str, spec: Any, exported: Any = None) -> None:
        """Re-create a saved figure (documents); layers keep their node ids."""
        with self._lock:
            if fid in self._docs:
                raise FigureSpecError(f"figure id {fid!r} already exists")
            doc = FigureDoc(fid, normalize(spec, set(self._session.node_ids())))
            doc.exported = exported if isinstance(exported, dict) else None
            self._docs[fid] = doc
            if fid.startswith("f") and fid[1:].isdigit():
                self._next = max(self._next, int(fid[1:]) + 1)
            self._changed(doc)

    def update(self, fid: str, spec: Any) -> dict[str, Any]:
        with self._lock:
            doc = self._doc(fid)
            new = normalize(spec, set(self._session.node_ids()))
            if new["name"] != doc.spec["name"] and new["name"] in self._taken(exclude=doc.id):
                raise FigureSpecError(f"name: {new['name']!r} is already used")
            if new == doc.spec:
                return doc.state()
            doc.undo.append(doc.spec)
            del doc.undo[:-MAX_UNDO]
            doc.redo.clear()
            doc.spec = new
            doc.version += 1
            return self._changed(doc)

    def undo(self, fid: str) -> dict[str, Any]:
        with self._lock:
            doc = self._doc(fid)
            if doc.undo:
                doc.redo.append(doc.spec)
                doc.spec = doc.undo.pop()
                doc.version += 1
                return self._changed(doc)
            return doc.state()

    def redo(self, fid: str) -> dict[str, Any]:
        with self._lock:
            doc = self._doc(fid)
            if doc.redo:
                doc.undo.append(doc.spec)
                doc.spec = doc.redo.pop()
                doc.version += 1
                return self._changed(doc)
            return doc.state()

    def set_spec(self, fid: str, spec: dict[str, Any]) -> None:
        """Put back a spec (graph undo); the figure's own history is not touched."""
        with self._lock:
            doc = self._docs.get(fid)
            if doc is None:
                return
            doc.spec = normalize(spec, set(self._session.node_ids()))
            doc.version += 1
            self._changed(doc)

    def delete(self, fid: str) -> None:
        with self._lock:
            doc = self._doc(fid)
            del self._docs[doc.id]
            self._session.rev += 1
        self._session._emit("figure.deleted", {"id": doc.id})

    def drop_sources(self, ids: set[str]) -> list[str]:
        """Remove layers drawing deleted nodes; returns the figures that changed."""
        changed = []
        with self._lock:
            for doc in self._docs.values():
                if not ids & set(doc.sources()):
                    continue
                spec = {**doc.spec, "axes": [
                    {**axes, "layers": [ly for ly in axes["layers"] if ly["source"] not in ids]}
                    for axes in doc.spec["axes"]
                ]}  # fmt: skip
                doc.undo.clear()  # history would point at deleted nodes
                doc.redo.clear()
                doc.spec = normalize(spec, set(self._session.node_ids()))
                doc.version += 1
                changed.append(doc)
        for doc in changed:
            self._changed(doc)
        return [d.id for d in changed]

    # ---- data -----------------------------------------------------------------------------------
    def fields(self, node: str, timeout: float = 30.0) -> dict[str, Any]:
        nid = self._session.node(node).id
        out = fields(self._session.wait(nid, timeout))
        out["id"] = nid
        return out

    def suggest(self, node: str, timeout: float = 30.0) -> list[dict[str, Any]]:
        nid = self._session.node(node).id
        try:
            value = self._session.wait(nid, timeout)
        except (NodeError, NotReady):
            return []
        return suggestions(value, nid)

    def default_layer(self, node: str, kind: str, timeout: float = 30.0) -> dict[str, Any]:
        if kind not in KINDS:
            raise BadRequest(f"unknown chart kind {kind!r}")
        nid = self._session.node(node).id
        return default_layer(self._session.wait(nid, timeout), nid, kind)

    def _code(self, doc: FigureDoc, timeout: float) -> tuple[FigureCode, dict[str, Any]]:
        names = self._session.variable_names()
        values: dict[str, Any] = {}
        for sid in doc.sources():
            try:
                values[sid] = self._session.wait(sid, timeout)
            except (NodeError, UnknownNode, KeyError):
                continue
        code = generate(doc.spec, names, values, taken=self._taken(exclude=doc.id))
        env = {names[sid]: v for sid, v in values.items()}
        return code, env

    def _axes_var(self, code: FigureCode) -> str:
        return code.blocks[0].executed[1].split(" = ", 1)[0]

    # ---- output ---------------------------------------------------------------------------------
    def code(self, fid: str, mode: str = "full", timeout: float = 30.0) -> str:
        with self._lock:
            doc = self._doc(fid)
            exported = doc.exported
        code, _ = self._code(doc, timeout)
        savefig = None
        if exported:
            args = [emit_literal(exported["path"]), f"dpi={exported['dpi']}"]
            if exported.get("transparent"):
                args.append("transparent=True")
            savefig = f"{code.fig_var}.savefig({', '.join(args)})"
        style = self._session.code_style()
        figure = code.display(savefig=savefig)
        if mode == "figure":
            return restyle(figure, style)
        sources = []
        for sid in doc.sources():
            if sid in self._session:
                sources += [n for n in self._session.lineage(sid) if n not in sources]
        order = [nid for nid in self._session.node_ids() if nid in set(sources)]
        if style.chained:
            from ..codegen.chain import chained_lines

            present = [sid for sid in doc.sources() if sid in self._session]
            pipeline = "\n".join(chained_lines(self._session, present, style))
        else:
            pipeline = "\n".join(pipeline_lines(self._session, order, style=style))
        used = used_modules(pipeline + "\n" + figure) | {"plt", "pd"}
        parts = ["\n".join(import_lines(used, style))] if style.include_imports else []
        if pipeline.strip():
            parts.append(restyle(pipeline, style))
        parts.append(restyle(figure, style) + f"\n{style.pyplot_alias}.show()")
        return "\n\n".join(parts) + "\n"

    def _build(self, doc: FigureDoc, timeout: float, preview_limit: int | None):
        code, env = self._code(doc, timeout)
        return code, build(code, env, self._axes_var(code), preview_limit=preview_limit)

    def render(
        self,
        fid: str,
        width_px: int | None = None,
        height_px: int | None = None,
        dpr: float = 1.0,
        timeout: float = 30.0,
    ) -> tuple[bytes, dict[str, Any]]:
        with self._lock:
            doc = self._doc(fid)
            spec, version = doc.spec, doc.version
        dpi = float(spec["dpi"])
        if width_px and height_px:
            fit = min(width_px / spec["width"], height_px / spec["height"])
            dpi = max(10.0, min(300.0, fit * max(0.5, min(dpr, 2.0))))
        with style_context(spec["style"]):
            _, out = self._build(doc, timeout, PREVIEW_ROWS)
            png, width, height = png_bytes(out.figure, dpi)
        meta = {
            "id": doc.id,
            "version": version,
            "width": width,
            "height": height,
            "sampled": out.sampled,
            "errors": [{"axes": k, "layer": j, "message": m} for (k, j), m in out.errors.items()],
            "warnings": out.warnings[:20],
        }
        return png, meta

    def figure(self, fid: str, timeout: float = 30.0) -> Figure:
        """The figure drawn with all the data (what exports and ``res.figures`` use)."""
        with self._lock:
            doc = self._doc(fid)
        with style_context(doc.spec["style"]):
            _, out = self._build(doc, timeout, None)
            out.figure.canvas.draw()
        return out.figure

    def export(
        self,
        fid: str,
        fmt: str = "png",
        dpi: int | None = None,
        transparent: bool = False,
        path: str | None = None,
        timeout: float = 60.0,
    ) -> tuple[bytes, dict[str, Any]]:
        if fmt not in catalog()["formats"]:
            raise BadRequest(f"format must be one of {', '.join(catalog()['formats'])}")
        with self._lock:
            doc = self._doc(fid)
        dpi = doc.spec["dpi"] if dpi is None else dpi
        if isinstance(dpi, bool) or not isinstance(dpi, int) or not 30 <= dpi <= 1200:
            raise BadRequest("dpi must be an integer between 30 and 1200")
        target: Path | None = None
        if path is not None:
            if not isinstance(path, str) or not path.strip():
                raise BadRequest("path must be a file name")
            target = Path(path).expanduser()
            if not target.is_absolute():
                target = Path.cwd() / target
            suffixes = {"jpg": (".jpg", ".jpeg")}.get(fmt, (f".{fmt}",))
            if target.suffix.lower() not in suffixes:
                raise BadRequest(f"the file name must end in {suffixes[0]}")
            if target.is_dir() or not target.parent.is_dir():
                raise BadRequest(f"cannot write {target}: the folder does not exist")
        buffer = io.BytesIO()
        with style_context(doc.spec["style"]):
            _, out = self._build(doc, timeout, None)
            if out.errors:
                first = next(iter(out.errors.values()))
                raise FigureSpecError(f"fix the layers with errors before exporting ({first})")
            out.figure.savefig(buffer, format=fmt, dpi=dpi, transparent=transparent)
        data = buffer.getvalue()
        meta: dict[str, Any] = {"format": fmt, "bytes": len(data), "path": None}
        if target is not None:
            target.write_bytes(data)
            meta["path"] = str(target)
            with self._lock:
                doc.exported = {"path": path, "dpi": dpi, "transparent": transparent, "format": fmt}
            self._changed(doc)
        return data, meta

    def to_json(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"id": d.id, "spec": d.spec, "exported": d.exported} for d in self._docs.values()
            ]
