"""Session methods exposed over the protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import BadRequest
from ..ops import op_from_json
from ..ops.formula import parse_formula
from ..ops.values import value_to_json
from ..plot.kinds import catalog

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

__all__ = ["register_session_methods"]


def _int(params: dict[str, Any], key: str, default: int | None, *, minimum: int = 0) -> int | None:
    value = params.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BadRequest(f"{key} must be an integer >= {minimum}")
    return value


def _id(params: dict[str, Any]) -> str:
    value = params.get("id")
    if not isinstance(value, str) or not value:
        raise BadRequest("id must be a node id or name")
    return value


def _str(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise BadRequest(f"{key} is required")
    return value


def _number(params: dict[str, Any], key: str, default: float) -> float:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BadRequest(f"{key} must be a number")
    return float(value)


def register_session_methods(dispatcher: Dispatcher) -> None:
    from .dispatcher import Reply

    session = dispatcher.session

    def apply(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        node = session.apply(
            op_from_json(params.get("op")),
            name=params.get("name"),
            force=params.get("force") is True,
        )
        return {"node": node.info()}

    def summary(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        return session.summary(_id(params))

    def window(params: dict[str, Any], _buffers: list[bytes]) -> Reply:
        data, meta = session.window(
            _id(params),
            offset=_int(params, "offset", 0),
            limit=min(_int(params, "limit", 200), 5000),
            col_start=_int(params, "col_start", 0),
            col_stop=_int(params, "col_stop", None),
        )
        return Reply(meta, [data])

    def code(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        mode = params.get("mode", "origin")
        return {"code": session.code(_id(params), mode="step" if mode == "step" else "origin")}

    def preview(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        return session.preview(op_from_json(params.get("op")), name=params.get("name"))

    def delete_preview(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        return session.delete_preview(_id(params))

    def delete(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        return session.delete(_id(params))

    def formula(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        """Parse a new-column formula against a node's columns (nothing is created)."""
        from ..table import to_frame

        value = session.wait(_id(params), 30.0)
        frame = to_frame(value)
        columns = list(frame.columns) if frame is not None else []
        text = params.get("text", "")
        try:
            expr = parse_formula(text, columns)
        except Exception as exc:
            offset = getattr(exc, "offset", None)
            if getattr(exc, "code", None) != "invalid_formula":
                raise
            return {"ok": False, "message": str(exc), "offset": offset}
        return {"ok": True, "expr": value_to_json(expr)}

    # ---- plotter -----------------------------------------------------------------------------
    plots = session.plots

    def fid(params: dict[str, Any]) -> str:
        return _str(params, "id")

    dispatcher.register("plot.catalog", lambda params, _b: catalog())
    dispatcher.register("plot.fields", lambda params, _b: plots.fields(_id(params)))
    dispatcher.register("plot.suggest", lambda params, _b: {"layers": plots.suggest(_id(params))})
    dispatcher.register(
        "plot.default_layer",
        lambda params, _b: plots.default_layer(_id(params), _str(params, "kind")),
    )
    dispatcher.register(
        "figure.create",
        lambda params, _b: plots.create(params.get("source"), name=params.get("name")),
    )
    dispatcher.register("figure.get", lambda params, _b: plots.get(fid(params)))
    dispatcher.register(
        "figure.update", lambda params, _b: plots.update(fid(params), params.get("spec"))
    )
    dispatcher.register("figure.undo", lambda params, _b: plots.undo(fid(params)))
    dispatcher.register("figure.redo", lambda params, _b: plots.redo(fid(params)))

    def figure_delete(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        plots.delete(fid(params))
        return {"deleted": True}

    def figure_code(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        mode = "figure" if params.get("mode") == "figure" else "full"
        return {"code": plots.code(fid(params), mode=mode)}

    def figure_render(params: dict[str, Any], _buffers: list[bytes]) -> Reply:
        width = _int(params, "width_px", None, minimum=1)
        height = _int(params, "height_px", None, minimum=1)
        png, meta = plots.render(
            fid(params),
            width_px=min(width, 4000) if width else None,
            height_px=min(height, 4000) if height else None,
            dpr=_number(params, "dpr", 1.0),
        )
        return Reply(meta, [png])

    def figure_export(params: dict[str, Any], _buffers: list[bytes]) -> Reply:
        data, meta = plots.export(
            fid(params),
            fmt=params.get("format", "png"),
            dpi=params.get("dpi"),
            transparent=params.get("transparent") is True,
            path=params.get("path"),
        )
        return Reply(meta, [data] if params.get("download") else [])

    dispatcher.register("figure.delete", figure_delete)
    dispatcher.register("figure.code", figure_code)
    dispatcher.register("figure.render", figure_render)
    dispatcher.register("figure.export", figure_export)

    def rename(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise BadRequest("name must be a non-empty string")
        return {"renamed": session.rename(_id(params), name)}

    def edit_as_new(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        mapping = session.edit_as_new(
            _id(params),
            op_from_json(params.get("op")),
            replay=params.get("replay", True) is not False,
            name=params.get("name"),
        )
        return {"mapping": mapping}

    def pins(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        ids = params.get("ids", [])
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise BadRequest("ids must be a list of node ids")
        return {"pinned": session.set_pins(ids)}

    def catalog_members(params: dict[str, Any], _buffers: list[bytes]) -> dict[str, Any]:
        from ..catalog import load

        catalog = load()
        owner = params.get("owner")
        if owner not in catalog.owners:
            raise BadRequest(f"owner must be one of {', '.join(catalog.owners)}")
        members = [m.describe() for m in catalog.members(owner)]
        return {"pandas_version": catalog.pandas_version, "members": members}

    dispatcher.register("catalog.members", catalog_members)
    dispatcher.register(
        "node.members", lambda params, _b: {"members": session.members(_id(params))}
    )
    dispatcher.register(
        "session.export",
        lambda params, _b: session.export(params.get("format", "py"), path=params.get("path")),
    )
    dispatcher.register("session.pins", pins)
    dispatcher.register("node.rename", rename)
    dispatcher.register("node.edit_as_new", edit_as_new)
    dispatcher.register(
        "node.cancel", lambda params, _b: {"cancelled": session.cancel(_id(params))}
    )
    dispatcher.register("node.retry", lambda params, _b: {"ids": session.retry(_id(params))})
    dispatcher.register("graph.clear_failed", lambda params, _b: session.clear_failed())
    dispatcher.register("graph.undo", lambda params, _b: {"done": session.undo()})
    dispatcher.register("graph.redo", lambda params, _b: {"done": session.redo()})
    dispatcher.register("node.delete_preview", delete_preview)
    dispatcher.register("node.delete", delete)
    dispatcher.register("formula.parse", formula)
    dispatcher.register("node.apply", apply)
    dispatcher.register("op.preview", preview)
    dispatcher.register("node.summary", summary)
    dispatcher.register("node.window", window)
    dispatcher.register("node.code", code)
