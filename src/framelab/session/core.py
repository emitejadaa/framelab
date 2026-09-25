"""Session: the Python-side source of truth for the graph of nodes."""

from __future__ import annotations

import logging
import secrets
import threading
import traceback
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

import pandas as pd

from ..codegen.render import op_label, render_op
from ..codegen.style import CodeStyle, restyle
from ..engine import ComputeLane, run_statement
from ..errors import FramelabError
from ..naming import RootSpec, auto_node_name, sanitize_identifier
from ..ops import Op
from ..options import OptionsRegistry
from ..options import registry as default_registry
from ..protocol.schema import SessionSnapshot
from .figures import FigureStore
from .node import ErrorDetail, Node, NodeError, NodeState, NotReady, UnknownNode, classify

__all__ = ["CannotDelete", "Session"]

log = logging.getLogger("framelab")

Listener = Callable[[str, dict[str, Any]], None]
_DEAD = (NodeState.ERROR, NodeState.BLOCKED)


class CannotDelete(FramelabError, ValueError):
    code = "cannot_delete"


class Session:
    """Everything a framelab UI shows; also what ``fl.explore()`` returns."""

    def __init__(self, roots: list[RootSpec], options: OptionsRegistry | None = None) -> None:
        self.id = secrets.token_hex(8)
        self.rev = 0
        self._options = options if options is not None else default_registry
        self._lock = threading.RLock()
        self._nodes: dict[str, Node] = {}
        self._by_name: dict[str, str] = {}
        self._results: dict[str, Any] = {}
        self._futures: dict[str, Future] = {}
        self._listeners: list[Listener] = []
        self._next = 1
        self._lane = ComputeLane()
        self._encoders: dict[str, Any] = {}
        self.widget: Any = None
        self.plots = FigureStore(self)
        for spec in roots:
            if not isinstance(spec.obj, (pd.DataFrame, pd.Series)):
                raise TypeError(
                    "framelab.explore expects pandas DataFrame or Series objects; "
                    f"got {type(spec.obj).__name__} for {spec.name!r}"
                )
            # Copy-on-Write: a shallow copy freezes the root at no memory cost.
            frozen = spec.obj.copy(deep=False)
            kind, shape = classify(frozen)
            node = Node(
                id=self._take_id(None),
                name=spec.name,
                op=None,
                name_auto=False,
                source_expr=spec.source_expr,
                state=NodeState.READY,
                kind=kind,
                shape=shape,
            )
            self._register(node)
            self._results[node.id] = frozen
            done: Future = Future()
            done.set_result(frozen)
            self._futures[node.id] = done

    # ---- lookup ------------------------------------------------------------------------
    def _take_id(self, wanted: str | None) -> str:
        if wanted is None:
            nid = f"n{self._next}"
        else:
            if wanted in self._nodes:
                raise ValueError(f"node id {wanted!r} already exists")
            nid = wanted
        if nid.startswith("n") and nid[1:].isdigit():
            self._next = max(self._next, int(nid[1:]) + 1)
        return nid

    def _register(self, node: Node) -> None:
        self._nodes[node.id] = node
        self._by_name[node.name] = node.id
        self.rev += 1

    def _resolve(self, key: str) -> str:
        if key in self._nodes:
            return key
        if key in self._by_name:
            return self._by_name[key]
        raise UnknownNode(f"no node called {key!r}")

    def node(self, key: str) -> Node:
        with self._lock:
            return self._nodes[self._resolve(key)]

    def nodes(self) -> list[Node]:
        with self._lock:
            return list(self._nodes.values())

    @property
    def names(self) -> list[str]:
        return [n.name for n in self.nodes()]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and (key in self._nodes or key in self._by_name)

    def __len__(self) -> int:
        return len(self._nodes)

    def __iter__(self) -> Iterator[str]:
        return iter(self.names)

    def source_expr(self, key: str) -> str | None:
        return self.node(key).source_expr

    def node_ids(self) -> list[str]:
        with self._lock:
            return list(self._nodes)

    def variable_names(self) -> dict[str, str]:
        with self._lock:
            return {nid: n.name for nid, n in self._nodes.items()}

    # ---- graph ---------------------------------------------------------------------------
    def apply(self, op: Op, *, name: str | None = None, node_id: str | None = None) -> Node:
        """Create a node for ``op``; its result is computed on the compute lane."""
        op.validate()
        with self._lock:
            for parent in op.parents():
                if parent not in self._nodes:
                    raise UnknownNode(f"no node with id {parent!r}")
            names = self.variable_names()
            if name is None:
                final, auto = auto_node_name(op, names, self._by_name), True
            else:
                final, auto = sanitize_identifier(name), False
                if final in self._by_name:
                    raise ValueError(f"a node called {final!r} already exists")
            node = Node(
                id=self._take_id(node_id),
                name=final,
                op=op,
                parents=op.parents(),
                name_auto=auto,
                label=op_label(op, names),
            )
            self._register(node)
            if any(self._nodes[p].state in _DEAD for p in node.parents):
                node.state = NodeState.BLOCKED
                failed: Future = Future()
                failed.set_exception(NodeError(node))
                self._futures[node.id] = failed
            else:
                self._futures[node.id] = self._lane.submit(self._compute, node.id)
            info = node.info()
        self._emit("node.upserted", info)
        return node

    def preview(self, op: Op, *, name: str | None = None) -> dict[str, str]:
        """The code ``apply(op)`` would show, without creating the node."""
        op.validate()
        with self._lock:
            for parent in op.parents():
                if parent not in self._nodes:
                    raise UnknownNode(f"no node with id {parent!r}")
            names = self.variable_names()
            final = sanitize_identifier(name) if name else auto_node_name(op, names, self._by_name)
        style = self.code_style()
        return {
            "name": final,
            "code": restyle(render_op(op, final, names, style).display, style),
            "label": op_label(op, names),
        }

    def descendants(self, key: str) -> list[str]:
        """The node and everything computed from it, in creation order."""
        with self._lock:
            doomed = {self._resolve(key)}
            for nid, node in self._nodes.items():  # creation order = topological order
                if doomed & set(node.parents):
                    doomed.add(nid)
            return [nid for nid in self._nodes if nid in doomed]

    def delete_preview(self, key: str) -> dict[str, Any]:
        """What :meth:`delete` would remove (for a confirmation)."""
        ids = self.descendants(key)
        figures = [f for f in self.plots.infos() if set(f["sources"]) & set(ids)]
        return {
            "ids": ids,
            "names": [self._nodes[i].name for i in ids],
            "figures": [f["name"] for f in figures],
        }

    def delete(self, key: str) -> dict[str, Any]:
        """Remove a node and all its descendants (roots are the input data and stay)."""
        with self._lock:
            nid = self._resolve(key)
            if self._nodes[nid].is_root:
                raise CannotDelete(f"{self._nodes[nid].name} is data passed to fl.explore()")
            ids = self.descendants(nid)
            for i in ids:
                node = self._nodes.pop(i)
                if self._by_name.get(node.name) == i:
                    del self._by_name[node.name]
                self._results.pop(i, None)
                self._encoders.pop(i, None)
                future = self._futures.pop(i, None)
                if future is not None:
                    future.cancel()
            self.rev += 1
        self._emit("node.deleted", {"ids": ids})
        figures = self.plots.drop_sources(set(ids))
        return {"ids": ids, "figures": figures}

    def _compute(self, nid: str) -> Any:
        with self._lock:
            node = self._nodes.get(nid)
            if node is None:  # deleted while it was queued
                raise UnknownNode(f"node {nid!r} was deleted")
            if any(self._nodes[p].state in _DEAD for p in node.parents):
                node.state = NodeState.BLOCKED
                self.rev += 1
                blocked_info = node.info()
            else:
                blocked_info = None
                node.state = NodeState.COMPUTING
                self.rev += 1
                env = {self._nodes[p].name: self._results[p] for p in node.parents}
                rendered = render_op(node.op, node.name, self.variable_names())  # type: ignore[arg-type]
                info = node.info()
        if blocked_info is not None:
            self._emit("node.state", blocked_info)
            raise NodeError(node)
        self._emit("node.state", info)
        try:
            value, warns = run_statement(rendered.executed, node.name, env)
        except Exception as exc:
            with self._lock:
                node.state = NodeState.ERROR
                node.error = ErrorDetail(type(exc).__name__, str(exc), traceback.format_exc())
                self.rev += 1
                info = node.info()
            self._emit("node.state", info)
            raise NodeError(node) from exc
        with self._lock:
            if self._nodes.get(nid) is not node:  # deleted while computing
                return value
            self._results[nid] = value
            node.kind, node.shape = classify(value)
            node.warnings = tuple(warns)
            node.state = NodeState.READY
            self.rev += 1
            info = node.info()
        self._emit("node.state", info)
        return value

    def wait(self, key: str, timeout: float | None = None) -> Any:
        """The node's value, waiting for its computation (raises NodeError on failure)."""
        with self._lock:
            future = self._futures[self._resolve(key)]
        try:
            return future.result(timeout)
        except FutureTimeout:
            raise NotReady(f"{key} is still computing") from None

    def __getitem__(self, key: str) -> Any:
        return self.wait(key)

    def lineage(self, key: str) -> list[str]:
        """Ids of the node and all its ancestors, in creation (= topological) order."""
        with self._lock:
            wanted: set[str] = set()
            stack = [self._resolve(key)]
            while stack:
                nid = stack.pop()
                if nid not in wanted:
                    wanted.add(nid)
                    stack.extend(self._nodes[nid].parents)
            return [nid for nid in self._nodes if nid in wanted]

    def code_style(self) -> CodeStyle:
        """The code style from ``fl.options``, never shadowing a node's variable."""
        return CodeStyle.from_options(self._options).safe_for(set(self.names))

    def code(self, key: str, mode: str = "origin", style: CodeStyle | None = None) -> str:
        from ..codegen.script import node_script

        return node_script(self, key, mode=mode, style=style)

    def window(
        self,
        key: str,
        offset: int = 0,
        limit: int = 200,
        col_start: int = 0,
        col_stop: int | None = None,
        timeout: float = 30.0,
    ) -> tuple[bytes, dict]:
        """Arrow IPC bytes + metadata for a block of rows (and optionally of columns)."""
        from ..table import NotTabular, WindowEncoder, to_frame

        nid = self._resolve(key)
        value = self.wait(nid, timeout)
        with self._lock:
            encoder = self._encoders.get(nid)
            if encoder is None:
                frame = to_frame(value)
                if frame is None:
                    raise NotTabular(f"{self._nodes[nid].name} is not a table")
                encoder = self._encoders[nid] = WindowEncoder(frame)
        return encoder.encode(offset, limit, col_start, col_stop)

    def summary(self, key: str, timeout: float = 30.0) -> dict:
        from ..table import summarize

        nid = self._resolve(key)
        out = summarize(self.wait(nid, timeout))
        out["id"] = nid
        out["name"] = self._nodes[nid].name
        return out

    # ---- events and snapshot -----------------------------------------------------------------
    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _emit(self, method: str, params: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(method, params)
            except Exception:  # a broken listener must never stall the graph
                log.exception("framelab: event listener failed on %s", method)

    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return {
                "rev": self.rev,
                "session_id": self.id,
                "nodes": [n.info() for n in self._nodes.values()],
                "figures": self.plots.infos(),  # type: ignore[typeddict-item]
                "options": self._options.describe(),  # type: ignore[typeddict-item]
            }

    @property
    def figures(self) -> dict[str, Any]:
        """Every figure drawn with all its data: ``{name: matplotlib Figure}``."""
        out = {}
        for fid in self.plots.ids():
            figure = self.plots.figure(fid)
            out[self.plots.get(fid)["spec"]["name"]] = figure
        return out

    def close(self) -> None:
        self._lane.shutdown(wait=False)

    def __repr__(self) -> str:
        return f"<framelab.Session {self.id}: {', '.join(self.names)}>"
