"""The pandas catalog: every member framelab can offer, with category, parameters, return kind,
mutation flag and preview policy.

``tools/gen_catalog.py`` builds ``pandas.json.gz`` from the reference pandas; this module reads
it. Members a newer pandas adds still show up, found by introspection, under "Other".
"""

from __future__ import annotations

import functools
import gzip
import inspect
import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from ..ops.policy import method_allowed

__all__ = ["OTHER", "Catalog", "Member", "Param", "load", "owner_types"]

OTHER = "Other"


@dataclass(frozen=True)
class Param:
    name: str
    widget: str = "value"
    required: bool = False
    default: Any = None
    choices: tuple[Any, ...] = ()
    annotation: str = ""
    variadic: str = ""

    def describe(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "widget": self.widget,
            "required": self.required,
            "annotation": self.annotation,
        }
        if not self.required and not self.variadic:
            out["default"] = self.default
        if self.choices:
            out["choices"] = list(self.choices)
        if self.variadic:
            out["variadic"] = self.variadic
        return out


@dataclass(frozen=True)
class Member:
    owner: str
    name: str
    kind: str
    category: str = OTHER
    summary: str = ""
    params: tuple[Param, ...] = ()
    returns: str = "unknown"
    mutates: bool = False
    preview: str = "global"
    allowed: bool = True
    generated: bool = True

    def describe(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "name": self.name,
            "kind": self.kind,
            "category": self.category,
            "summary": self.summary,
            "params": [p.describe() for p in self.params],
            "returns": self.returns,
            "mutates": self.mutates,
            "preview": self.preview,
            "allowed": self.allowed,
            "generated": self.generated,
        }


def _param(raw: dict[str, Any]) -> Param:
    return Param(
        name=raw["name"],
        widget=raw.get("widget", "value"),
        required=raw.get("required", False),
        default=raw.get("default"),
        choices=tuple(raw.get("choices") or ()),
        annotation=raw.get("annotation", ""),
        variadic=raw.get("variadic", ""),
    )


def _member(owner: str, raw: dict[str, Any]) -> Member:
    return Member(
        owner=owner,
        name=raw["name"],
        kind=raw["kind"],
        category=raw.get("category", OTHER),
        summary=raw.get("summary", ""),
        params=tuple(_param(p) for p in raw.get("params", [])),
        returns=raw.get("returns", "unknown"),
        mutates=raw.get("mutates", False),
        preview=raw.get("preview", "global"),
        allowed=raw.get("allowed", True),
    )


@functools.cache
def owner_types() -> dict[str, type]:
    """The runtime class behind every owner (used for members missing from the file)."""
    import pandas as pd
    from pandas.api.typing import (
        DataFrameGroupBy,
        Expanding,
        ExponentialMovingWindow,
        Rolling,
        SeriesGroupBy,
    )

    t = pd.DataFrame(
        {
            "s": pd.array(["x"], dtype="str"),
            "t": pd.to_datetime(["2020-01-01"]),
            "c": pd.Categorical(["u"]),
        }
    )
    return {
        "DataFrame": pd.DataFrame,
        "Series": pd.Series,
        "Index": pd.Index,
        "DataFrameGroupBy": DataFrameGroupBy,
        "SeriesGroupBy": SeriesGroupBy,
        "Resampler": type(t.set_index("t").resample("D")),
        "Rolling": Rolling,
        "Expanding": Expanding,
        "ExponentialMovingWindow": ExponentialMovingWindow,
        "str": type(t["s"].str),
        "dt": type(t["t"].dt),
        "cat": type(t["c"].cat),
    }


def _introspect(owner: str, name: str) -> Member | None:
    cls = owner_types().get(owner)
    if cls is None or name.startswith("_"):
        return None
    try:
        raw = inspect.getattr_static(cls, name)
    except AttributeError:
        return None
    doc = inspect.getdoc(raw) or ""
    summary = " ".join(doc.strip().split("\n\n", 1)[0].split())[:240]
    method = inspect.isfunction(raw) or inspect.ismethoddescriptor(raw) or inspect.isbuiltin(raw)
    params: tuple[Param, ...] = ()
    if method:
        try:
            sig = inspect.signature(raw)
        except (TypeError, ValueError):
            sig = None
        if sig is not None:
            variadic = {inspect.Parameter.VAR_POSITIONAL: "*", inspect.Parameter.VAR_KEYWORD: "**"}
            params = tuple(
                Param(
                    p.name,
                    required=p.default is p.empty and p.kind not in variadic,
                    variadic=variadic.get(p.kind, ""),
                )
                for p in sig.parameters.values()
                if p.name != "self"
            )
    kind = "method" if method else "property"
    allowed = method_allowed(name)
    return Member(owner, name, kind, OTHER, summary, params, allowed=allowed, generated=False)


class Catalog:
    def __init__(self, data: dict[str, Any]) -> None:
        self.pandas_version: str = data["pandas_version"]
        self._members: dict[str, dict[str, Member]] = {
            owner: {m["name"]: _member(owner, m) for m in body["members"]}
            for owner, body in data["owners"].items()
        }
        self._deprecated = {
            owner: set(body.get("deprecated", [])) for owner, body in data["owners"].items()
        }

    @property
    def owners(self) -> list[str]:
        return list(self._members)

    def member(self, owner: str, name: str) -> Member | None:
        found = self._members.get(owner, {}).get(name)
        if found is not None or name in self._deprecated.get(owner, ()):
            return found
        return _introspect(owner, name)

    def members(self, owner: str) -> list[Member]:
        known = self._members.get(owner, {})
        out = list(known.values())
        cls = owner_types().get(owner)
        if cls is not None:
            skip = set(known) | self._deprecated.get(owner, set())
            for name in sorted(dir(cls)):
                if not name.startswith("_") and name not in skip:
                    extra = _introspect(owner, name)
                    if extra is not None:
                        out.append(extra)
        return out


@functools.cache
def load() -> Catalog:
    raw = resources.files(__package__).joinpath("pandas.json.gz").read_bytes()
    return Catalog(json.loads(gzip.decompress(raw)))
