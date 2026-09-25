"""Session: the Python-side source of truth for the graph of nodes."""

from __future__ import annotations

import contextlib
import logging
import secrets
import threading
import traceback
from collections.abc import Callable, Iterator
from concurrent.futures import CancelledError, Future
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

import pandas as pd
import psutil

from ..codegen.render import op_label, render_op
from ..codegen.style import CodeStyle, restyle
from ..engine import ComputeLane, guards, run_statement
from ..engine.cache import ResultCache, buffers, default_budget, value_bytes
from ..errors import FramelabError
from ..naming import RootSpec, auto_node_name, op_alias, sanitize_identifier, unique_name
from ..ops import Op, remap_op
from ..options import OptionsRegistry
from ..options import registry as default_registry
from ..protocol.schema import SessionSnapshot
from .figures import FigureStore
from .history import Change, History, NodeRecord
from .node import ErrorDetail, Node, NodeError, NodeState, NotReady, UnknownNode, classify

__all__ = ["CannotDelete", "CannotEdit", "CannotRename", "NameTaken", "Session"]

log = logging.getLogger("framelab")

Listener = Callable[[str, dict[str, Any]], None]
_DEAD = (NodeState.ERROR, NodeState.BLOCKED, NodeState.CANCELLED)


class CannotDelete(FramelabError, ValueError):
    code = "cannot_delete"


class CannotRename(FramelabError, ValueError):
    code = "cannot_rename"


class NameTaken(FramelabError, ValueError):
    code = "name_taken"


class CannotEdit(FramelabError, ValueError):
    code = "cannot_edit"


class Session:
    """Everything a framelab UI shows; also what ``fl.explore()`` returns."""

    def __init__(
        self,
        roots: list[RootSpec],
        options: OptionsRegistry | None = None,
        *,
        guard_bytes: int | None = None,
        cache_bytes: int | None = None,
    ) -> None:
        self.id = secrets.token_hex(8)
        self._guard_bytes = guard_bytes
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
        self._history = History()
        self._replaying = 0
        self._batch: Change | None = None
        budget = cache_bytes
        if budget is None:
            budget = default_budget(self._options.get("performance.cache_fraction"))
        self._cache = ResultCache(budget)
        self._root_buffers: set[int] = set()
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
                alias=spec.name,
                op=None,
                name_auto=False,
                source_expr=spec.source_expr,
                state=NodeState.READY,
                kind=kind,
                shape=shape,
            )
            self._register(node)
            self._results[node.id] = frozen
            self._root_buffers.update(address for address, _ in buffers(frozen))
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
    def apply(
        self, op: Op, *, name: str | None = None, node_id: str | None = None, force: bool = False
    ) -> Node:
        """Create a node for ``op``; its result is computed on the compute lane.

        Guards refuse results that would not fit in memory (GuardError) unless ``force``.
        """
        op.validate()
        self._check_parents(op)
        if not force and not self._replaying:
            values = self._ready_values(op.parents())
            if values is not None:
                guards.check(op, values, limit_bytes=self._guard_limit())
        with self._lock:
            self._check_parents(op)
            names = self.variable_names()
            if name is None:
                trail = self._trail(op.target) if op.target else ()
                final, auto = auto_node_name(op, names, self._by_name, trail), True
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
                alias=op_alias(op, names),
                force=force,
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
            self._record(Change("create", nodes=[self._record_of(node)]))
        self._emit("node.upserted", info)
        return node

    def preview(self, op: Op, *, name: str | None = None) -> dict[str, str]:
        """The code ``apply(op)`` would show, without creating the node (guards included)."""
        op.validate()
        self._check_parents(op)
        values = self._ready_values(op.parents())
        if values is not None:
            guards.check(op, values, limit_bytes=self._guard_limit())
        with self._lock:
            names = self.variable_names()
            trail = self._trail(op.target) if op.target else ()
            final = (
                sanitize_identifier(name)
                if name
                else auto_node_name(op, names, self._by_name, trail)
            )
        style = self.code_style()
        return {
            "name": final,
            "code": restyle(render_op(op, final, names, style).display, style),
            "label": op_label(op, names),
        }

    def _trail(self, nid: str) -> tuple[str, ...]:
        """(root name, alias, alias, …) along the first-parent chain of ``nid``."""
        parts: list[str] = []
        node = self._nodes[nid]
        while not node.is_root:
            if node.alias:
                parts.append(node.alias)
            node = self._nodes[node.parents[0]]
        return (node.name, *reversed(parts))

    def _set_name(self, node: Node, name: str, auto: bool) -> None:
        if self._by_name.get(node.name) == node.id:
            del self._by_name[node.name]
        node.name, node.name_auto = name, auto
        self._by_name[name] = node.id

    def rename(self, key: str, new_name: str) -> list[str]:
        """Rename a node; auto-named descendants follow. Returns the ids whose name changed."""
        with self._lock:
            nid = self._resolve(key)
            node = self._nodes[nid]
            if node.is_root:
                raise CannotRename(f"{node.name} is your own variable: rename it in your code")
            final = sanitize_identifier(new_name)
            taken = (set(self._by_name) | self.plots.names()) - {node.name}
            if final in taken:
                raise NameTaken(f"{final!r} is already used")
            changes: list[tuple[str, str, bool, str, bool]] = []
            if final != node.name or node.name_auto:
                changes.append((nid, node.name, node.name_auto, final, False))
                self._set_name(node, final, False)
            touched = {nid}
            for d in self.descendants(nid)[1:]:
                child = self._nodes[d]
                names = self.variable_names()
                label = op_label(child.op, names)  # type: ignore[arg-type]
                if label != child.label:
                    child.label = label
                    touched.add(d)
                if child.name_auto:
                    others = (set(self._by_name) | self.plots.names()) - {child.name}
                    target = child.op.target  # type: ignore[union-attr]
                    trail = self._trail(target) if target else ()
                    fresh = auto_node_name(child.op, names, others, trail)
                    if fresh != child.name:
                        changes.append((d, child.name, True, fresh, True))
                        self._set_name(child, fresh, True)
                        touched.add(d)
                    child.alias = op_alias(child.op, names)
            if changes or len(touched) > 1:
                self.rev += 1
            self._after_rename(changes)
            infos = [n.info() for i, n in self._nodes.items() if i in touched]
        for info in infos:
            self._emit("node.upserted", info)
        return [c[0] for c in changes]

    def _after_rename(self, changes: list[tuple[str, str, bool, str, bool]]) -> None:
        if changes:
            self._record(Change("rename", names=changes))

    def _check_parents(self, op: Op) -> None:
        with self._lock:
            for parent in op.parents():
                if parent not in self._nodes:
                    raise UnknownNode(f"no node with id {parent!r}")

    def _guard_limit(self) -> int:
        if self._guard_bytes is not None:
            return self._guard_bytes
        fraction = self._options.get("performance.guard_ram_fraction")
        return int(psutil.virtual_memory().available * fraction)

    def _ready_values(self, ids: tuple[str, ...]) -> dict[str, Any] | None:
        """Parent values when every parent is ready (so guards can run before the node exists)."""
        with self._lock:
            out = {}
            for nid in ids:
                if self._nodes[nid].state is not NodeState.READY or nid not in self._results:
                    return None
                out[nid] = self._results[nid]
            return out

    def edit_as_new(
        self, key: str, op: Op, *, replay: bool = True, name: str | None = None
    ) -> dict[str, str]:
        """A sibling of ``key`` built from ``op``; with ``replay`` its descendants are rebuilt on
        the sibling. The original branch stays as it was. Returns old id -> new id."""
        original = self.node(key)
        if original.is_root:
            raise CannotEdit(f"{original.name} is data passed to fl.explore()")
        mapping: dict[str, str] = {}
        with self.batch():
            mapping[original.id] = self.apply(op, name=name).id
            if replay:
                for d in self.descendants(original.id)[1:]:
                    child = self.node(d)
                    taken = set(self.names) | self.plots.names()
                    wanted = None if child.name_auto else unique_name(child.name, taken)
                    new_op = remap_op(child.op, mapping)  # type: ignore[arg-type]
                    mapping[d] = self.apply(new_op, name=wanted, force=child.force).id
        return mapping

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

    def delete(self, *keys: str) -> dict[str, Any]:
        """Remove nodes and all their descendants (roots are the input data and stay)."""
        with self._lock:
            starts = [self._resolve(k) for k in keys]
            for nid in starts:
                if self._nodes[nid].is_root:
                    raise CannotDelete(f"{self._nodes[nid].name} is data passed to fl.explore()")
            doomed: set[str] = set()
            for nid in starts:
                doomed.update(self.descendants(nid))
            ids = [i for i in self._nodes if i in doomed]
            records = [self._record_of(self._nodes[i]) for i in ids]
            for i in ids:
                node = self._nodes.pop(i)
                if self._by_name.get(node.name) == i:
                    del self._by_name[node.name]
                self._results.pop(i, None)
                self._encoders.pop(i, None)
                self._cache.discard(i)
                future = self._futures.pop(i, None)
                if future is not None:
                    future.cancel()
            self.rev += 1
        self._emit("node.deleted", {"ids": ids})
        before = {
            f["id"]: self.plots.get(f["id"])["spec"]
            for f in self.plots.infos()
            if set(f["sources"]) & doomed
        }
        figures = self.plots.drop_sources(set(ids))
        self._record(Change("delete", nodes=records, figures=[(f, before[f]) for f in figures]))
        return {"ids": ids, "figures": figures}

    # ---- history ------------------------------------------------------------------------------
    @staticmethod
    def _record_of(node: Node) -> NodeRecord:
        return NodeRecord(node.id, node.name, node.name_auto, node.op, node.force)  # type: ignore[arg-type]

    def _record(self, change: Change) -> None:
        if self._replaying:
            return
        if self._batch is not None and change.kind == "create":
            self._batch.nodes.extend(change.nodes)
            return
        self._history.push(change)

    @contextlib.contextmanager
    def batch(self) -> Iterator[None]:
        """Every node created inside becomes one undo step."""
        outer = self._batch is None
        if outer:
            self._batch = Change("create")
        try:
            yield
        finally:
            if outer:
                change, self._batch = self._batch, None
                if change is not None and change.nodes:
                    self._history.push(change)

    @contextlib.contextmanager
    def _replay(self) -> Iterator[None]:
        self._replaying += 1
        try:
            yield
        finally:
            self._replaying -= 1

    def undo(self) -> bool:
        with self._lock:
            change = self._history.take_undo()
        if change is None:
            return False
        with self._replay():
            self._revert(change)
        with self._lock:
            self._history.undone(change)
        self._emit("graph.history", self._history.info())
        return True

    def redo(self) -> bool:
        with self._lock:
            change = self._history.take_redo()
        if change is None:
            return False
        with self._replay():
            self._reapply(change)
        with self._lock:
            self._history.done(change)
        self._emit("graph.history", self._history.info())
        return True

    def _revert(self, change: Change) -> None:
        if change.kind == "create":
            self._drop([r.id for r in change.nodes])
        elif change.kind == "delete":
            self._restore(change.nodes)
            for fid, spec in change.figures:
                self.plots.set_spec(fid, spec)
        else:
            for nid, old, old_auto, _new, _auto in reversed(change.names):
                self._rename_to(nid, old, old_auto)

    def _reapply(self, change: Change) -> None:
        if change.kind == "create":
            self._restore(change.nodes)
        elif change.kind == "delete":
            self._drop([r.id for r in change.nodes])
        else:
            for nid, _old, _old_auto, new, auto in change.names:
                self._rename_to(nid, new, auto)

    def _drop(self, ids: list[str]) -> None:
        existing = [i for i in ids if i in self._nodes]
        if existing:
            self.delete(*existing)

    def _restore(self, records: list[NodeRecord]) -> None:
        for r in records:
            if r.id in self._nodes:
                continue
            free = r.name not in self._by_name
            node = self.apply(r.op, name=r.name if free else None, node_id=r.id, force=r.force)
            with self._lock:
                node.name_auto = r.name_auto

    def _rename_to(self, nid: str, name: str, auto: bool) -> None:
        with self._lock:
            node = self._nodes.get(nid)
            if node is None:
                return
            if self._by_name.get(name, nid) != nid:
                name = unique_name(name, set(self._by_name))
            self._set_name(node, name, auto)
            names = self.variable_names()
            touched = [node]
            for d in self.descendants(nid)[1:]:
                child = self._nodes[d]
                child.label = op_label(child.op, names)  # type: ignore[arg-type]
                touched.append(child)
            self.rev += 1
            infos = [n.info() for n in touched]
        for info in infos:
            self._emit("node.upserted", info)

    def _compute(self, nid: str) -> Any:
        with self._lock:
            node = self._nodes.get(nid)
            if node is None:  # deleted while it was queued
                raise UnknownNode(f"node {nid!r} was deleted")
            if node.cancel_requested:  # cancelled just before it started
                node.cancel_requested = False
                node.state = NodeState.CANCELLED
                self.rev += 1
                blocked_info = node.info()
            elif any(self._nodes[p].state in _DEAD for p in node.parents):
                node.state = NodeState.BLOCKED
                self.rev += 1
                blocked_info = node.info()
            else:
                blocked_info = None
                node.state = NodeState.COMPUTING
                self.rev += 1
                names = self.variable_names()
                rendered = render_op(node.op, node.name, names)  # type: ignore[arg-type]
                info = node.info()
        if blocked_info is not None:
            self._emit("node.state", blocked_info)
            raise NodeError(node)
        self._emit("node.state", info)
        try:
            # freed parents are recomputed here, on the compute lane
            parent_values = {p: self._value(p) for p in node.parents}
            env = {names[p]: v for p, v in parent_values.items()}
            if not node.force:
                guards.check(node.op, parent_values, limit_bytes=self._guard_limit())  # type: ignore[arg-type]
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
            if node.cancel_requested:  # cancelled while computing: discard the result
                node.cancel_requested = False
                node.state = NodeState.CANCELLED
                self.rev += 1
                info = node.info()
                cancelled = True
            else:
                cancelled = False
        if cancelled:
            self._emit("node.state", info)
            raise NodeError(node)
        with self._lock:
            victims = self._store(nid, value)
            node.kind, node.shape = classify(value)
            node.warnings = tuple(warns)
            node.state = NodeState.READY
            self.rev += 1
            info = node.info()
        self._emit("node.state", info)
        self._evict(victims)
        return value

    # ---- memory ----------------------------------------------------------------------------
    def _store(self, nid: str, value: Any) -> list[str]:
        """Keep a result (lock held); returns the nodes to free to stay within budget."""
        self._results[nid] = value
        self._cache.add(nid, value_bytes(value, self._root_buffers))
        return self._cache.victims()

    def _evict(self, ids: list[str]) -> None:
        infos = []
        with self._lock:
            for nid in ids:
                node = self._nodes.get(nid)
                if node is None or node.state is not NodeState.READY or node.is_root:
                    continue
                self._results.pop(nid, None)
                self._encoders.pop(nid, None)
                self._futures.pop(nid, None)  # a finished future would keep the value alive
                self._cache.discard(nid)
                node.state = NodeState.FREED
                infos.append(node.info())
            if infos:
                self.rev += 1
        for info in infos:
            self._emit("node.state", info)

    def _value(self, nid: str) -> Any:
        """A node's value on the compute lane, recomputing freed ancestors first."""
        with self._lock:
            if nid in self._results:
                self._cache.touch(nid)
                return self._results[nid]
            node = self._nodes[nid]
            parents = node.parents
        values = {p: self._value(p) for p in parents}
        with self._lock:
            names = self.variable_names()
            rendered = render_op(node.op, node.name, names)  # type: ignore[arg-type]
        env = {names[p]: v for p, v in values.items()}
        value, _ = run_statement(rendered.executed, node.name, env)
        with self._lock:
            victims = self._store(nid, value)
            node.state = NodeState.READY
            self.rev += 1
            info = node.info()
        self._emit("node.state", info)
        self._evict([v for v in victims if v != nid])
        return value

    def set_pins(self, ids: list[str]) -> list[str]:
        """Nodes the UI shows (open tabs, figure sources): never freed while pinned."""
        with self._lock:
            self._cache.pinned = {i for i in ids if i in self._nodes}
            victims = self._cache.victims()
            pinned = sorted(self._cache.pinned)
        self._evict(victims)
        return pinned

    def wait(self, key: str, timeout: float | None = None) -> Any:
        """The node's value, waiting for its computation (raises NodeError on failure)."""
        info = None
        with self._lock:
            nid = self._resolve(key)
            node = self._nodes[nid]
            if node.state is NodeState.FREED:  # released from memory: compute it again
                node.state = NodeState.PENDING
                self._futures[nid] = self._lane.submit(self._value, nid)
                self.rev += 1
                info = node.info()
            future = self._futures[nid]
            self._cache.touch(nid)
        if info is not None:
            self._emit("node.state", info)
        try:
            return future.result(timeout)
        except FutureTimeout:
            raise NotReady(f"{key} is still computing") from None
        except CancelledError:
            raise NodeError(self._nodes[nid]) from None

    def cancel(self, key: str) -> bool:
        """Stop a node: queued ones never run; running ones finish and are discarded."""
        with self._lock:
            node = self._nodes[self._resolve(key)]
            if node.state not in (NodeState.PENDING, NodeState.COMPUTING):
                return False
            future = self._futures.get(node.id)
            if node.state is NodeState.PENDING and future is not None and future.cancel():
                node.state = NodeState.CANCELLED
            else:
                node.cancel_requested = True
            self.rev += 1
            info = node.info()
        self._emit("node.state", info)
        return True

    def retry(self, key: str) -> list[str]:
        """Run again the node and its failed, blocked or cancelled descendants."""
        with self._lock:
            again = [d for d in self.descendants(key) if self._nodes[d].state in _DEAD]
            for d in again:
                node = self._nodes[d]
                node.state = NodeState.PENDING
                node.error, node.warnings, node.cancel_requested = None, (), False
                self._futures[d] = self._lane.submit(self._compute, d)
            if again:
                self.rev += 1
            infos = [self._nodes[d].info() for d in again]
        for info in infos:
            self._emit("node.state", info)
        return again

    def clear_failed(self) -> dict[str, Any]:
        """Delete every node in error, blocked or cancelled (one undo step)."""
        with self._lock:
            failed = [i for i, n in self._nodes.items() if not n.is_root and n.state in _DEAD]
        return self.delete(*failed) if failed else {"ids": [], "figures": []}

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
                "history": self._history.info(),  # type: ignore[typeddict-item]
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
