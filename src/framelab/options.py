"""User preferences registry, exposed pandas-style as ``fl.options``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DEFAULT_OPTIONS",
    "Option",
    "OptionError",
    "OptionsNamespace",
    "OptionsRegistry",
    "build_default_registry",
    "get_option",
    "options",
    "registry",
    "reset_option",
    "set_option",
]

Listener = Callable[[str, Any], None]


class OptionError(ValueError):
    """An option was given a value of the wrong type or outside its choices."""


@dataclass(frozen=True)
class Option:
    key: str
    default: Any
    type: type
    choices: tuple[Any, ...] | None = None

    @property
    def category(self) -> str:
        return self.key.split(".", 1)[0]

    @property
    def i18n_key(self) -> str:
        return f"prefs.{self.key}"

    def validate(self, value: Any) -> Any:
        if self.type is bool:
            ok = isinstance(value, bool)
        elif self.type is int:
            ok = isinstance(value, int) and not isinstance(value, bool)
        elif self.type is float:
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            if ok:
                value = float(value)
        else:
            ok = isinstance(value, self.type)
        if not ok:
            raise OptionError(
                f"{self.key}: expected {self.type.__name__}, got {type(value).__name__}"
            )
        if self.choices is not None and value not in self.choices:
            raise OptionError(f"{self.key}: {value!r} is not one of {list(self.choices)}")
        return value


class OptionsRegistry:
    def __init__(self) -> None:
        self._defs: dict[str, Option] = {}
        self._values: dict[str, Any] = {}
        self._listeners: list[Listener] = []

    def register(self, option: Option) -> None:
        if option.key in self._defs:
            raise ValueError(f"option {option.key!r} is already registered")
        option.validate(option.default)
        self._defs[option.key] = option

    def definition(self, key: str) -> Option:
        try:
            return self._defs[key]
        except KeyError:
            raise KeyError(f"unknown option {key!r}") from None

    def get(self, key: str) -> Any:
        definition = self.definition(key)
        return self._values.get(key, definition.default)

    def set(self, key: str, value: Any) -> None:
        value = self.definition(key).validate(value)
        self._values[key] = value
        self._notify(key, value)

    def reset(self, key: str | None = None) -> None:
        keys = [key] if key is not None else list(self._values)
        for k in keys:
            definition = self.definition(k)
            if k in self._values:
                del self._values[k]
                self._notify(k, definition.default)

    def all_keys(self) -> list[str]:
        return sorted(self._defs)

    def has_prefix(self, prefix: str) -> bool:
        return any(k.startswith(prefix + ".") for k in self._defs)

    def describe(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for key in self.all_keys():
            d = self._defs[key]
            item: dict[str, Any] = {
                "key": key,
                "category": d.category,
                "value": self.get(key),
                "default": d.default,
                "type": d.type.__name__,
                "i18n_key": d.i18n_key,
            }
            if d.choices is not None:
                item["choices"] = list(d.choices)
            out.append(item)
        return out

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _notify(self, key: str, value: Any) -> None:
        for listener in list(self._listeners):
            listener(key, value)


class OptionsNamespace:
    """Attribute access over dotted keys: ``options.general.theme = "dark"``."""

    __slots__ = ("_prefix", "_registry")

    def __init__(self, registry: OptionsRegistry, prefix: str = "") -> None:
        object.__setattr__(self, "_registry", registry)
        object.__setattr__(self, "_prefix", prefix)

    def _full(self, name: str) -> str:
        return f"{self._prefix}.{name}" if self._prefix else name

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        full = self._full(name)
        if full in self._registry._defs:
            return self._registry.get(full)
        if self._registry.has_prefix(full):
            return OptionsNamespace(self._registry, full)
        raise AttributeError(f"no option {full!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        full = self._full(name)
        if full not in self._registry._defs:
            raise AttributeError(f"no option {full!r}")
        self._registry.set(full, value)

    def __dir__(self) -> list[str]:
        prefix = f"{self._prefix}." if self._prefix else ""
        return sorted(
            {
                k[len(prefix) :].split(".", 1)[0]
                for k in self._registry.all_keys()
                if k.startswith(prefix)
            }
        )

    def __repr__(self) -> str:
        prefix = f"{self._prefix}." if self._prefix else ""
        keys = [k for k in self._registry.all_keys() if k.startswith(prefix)]
        return "\n".join(f"{k} = {self._registry.get(k)!r}" for k in keys)


DEFAULT_OPTIONS: tuple[Option, ...] = (
    Option("general.language", "auto", str, ("auto", "es", "en")),
    Option("general.theme", "system", str, ("system", "light", "dark")),
    Option("general.accent", "#3B82F6", str),
    Option("general.open_mode", "auto", str, ("auto", "inline", "window")),
    Option("general.inline_height", 720, int),
    Option("general.reduce_motion", False, bool),
    Option("code.style", "steps", str, ("steps", "chained")),
    Option("code.filter_style", "mask", str, ("mask", "query")),
    Option("code.column_assign", "copy", str, ("copy", "assign")),
    Option("code.include_imports", True, bool),
    Option("code.quote", "double", str, ("double", "single")),
    Option("code.pandas_alias", "pd", str),
    Option("code.numpy_alias", "np", str),
    Option("code.pyplot_alias", "plt", str),
)


def build_default_registry() -> OptionsRegistry:
    reg = OptionsRegistry()
    for opt in DEFAULT_OPTIONS:
        reg.register(opt)
    return reg


registry = build_default_registry()
options = OptionsNamespace(registry)


def get_option(key: str) -> Any:
    return registry.get(key)


def set_option(key: str, value: Any) -> None:
    registry.set(key, value)


def reset_option(key: str | None = None) -> None:
    registry.reset(key)
