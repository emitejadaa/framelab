# M0 — Base, spikes y contratos · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `fl.explore(ventas)` opens a real framelab UI that shows "ventas · 1000 × 5", both from a script (native-like window, blocks, returns a `Session`) and inline in JupyterLab — on top of the final protocol, transport, security, packaging and CI contracts, with the 11 risky assumptions validated by throwaway spikes.

**Architecture:** Python owns all state (`Session`) and answers JSON envelopes (+ binary buffers) through a transport-agnostic `Dispatcher`. Two adapters: a token-protected Starlette/uvicorn WebSocket server (script/CLI, shown in Chromium `--app` / pywebview / browser tab) and an anywidget widget (notebooks). One single-file ESM React bundle (`framelab.js` + `framelab.css`) built by Vite into `src/framelab/_static/` and shipped inside a pure-Python wheel.

**Tech Stack:** Python 3.11–3.14, pandas 3.0.6, matplotlib 3.11.2, pyarrow 25, anywidget 0.11, starlette 1.7, uvicorn 0.53 (`ws="websockets-sansio"`), websockets 17, executing/varname, hatchling 1.32 · Node 24.21 + pnpm 12.6 (mise), React 19.3, Vite 8.3, TypeScript 7.0, Tailwind 4.3 (prefix `fl`), Zustand 5, i18next 26.

**Spec:** `docs/superpowers/specs/2026-09-23-framelab-design.md`

## Global Constraints

- Python ≥ 3.11 syntax only (no PEP 695 generics, no `type` statements); ruff `target-version = "py311"`.
- Runtime deps: `pandas>=3.0,<4`, `matplotlib>=3.11,<4`, `numpy>=1.26`, `pyarrow>=13`, `anywidget>=0.11`, `starlette>=0.40`, `uvicorn>=0.30`, `websockets>=13`, `varname[all]>=1.0`, `psutil>=5.9`, `platformdirs>=4`. Extras: `desktop = ["pywebview>=6.2"]`, `io = ["openpyxl", "tabulate", "jinja2", "lxml"]`.
- Never import `matplotlib.pyplot` in framelab's backend code.
- Local server: bind `127.0.0.1` only, random port, 32-byte token, token never on a command line, `Host` and `Origin` checks, no CORS.
- Frontend CSS scoped to `.fl-root`; Tailwind prefix `fl`; no global Preflight; every portal renders inside `.fl-root`.
- UI strings only through i18next (`es`, `en`); variable names never translated.
- Accent `#3B82F6`; greys only otherwise.
- **Test policy:** Python = TDD (pytest). Frontend = no TDD; optional scaffold tests only in `frontend/tests/scaffold/*.scaffold.test.ts`, excluded from CI and deleted at milestone close. E2E budget for the whole project is 6 flows; M0 uses #1 ("open window from script") implemented as a pytest slow test with headless Chromium.
- Commits: small, descriptive, straight to `main`, each ending with the two attribution lines:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Ks8wJ6dnQ283WhqQErFFQG
  ```
- Commands run from repo root `/home/tejada/Desktop/plotExp`; Python via `.venv/bin/python`; Node tooling via `mise exec -- pnpm …` inside `frontend/`.

## File map (M0)

```
pyproject.toml                         package metadata, deps, hatch config, pytest/ruff config
hatch_build.py                         build hook: builds the frontend bundle when missing
src/framelab/__init__.py               public API: explore, options, get/set/reset_option, last_session, __version__
src/framelab/_paths.py                 STATIC_DIR + require_static()
src/framelab/options.py                Option, OptionsRegistry, OptionsNamespace, default registry
src/framelab/env.py                    Env, detect_env(), resolve_mode()
src/framelab/naming.py                 RootSpec, sanitize_identifier(), unique_name(), resolve_root_names()
src/framelab/api.py                    explore(), last_session()
src/framelab/session/__init__.py       Session (M0: frozen roots + snapshot)
src/framelab/protocol/__init__.py      re-exports
src/framelab/protocol/schema.py        TypedDicts + PROTOCOL_VERSION (source of generated TS types)
src/framelab/protocol/codec.py         encode_frame/decode_frame, ProtocolError, dumps
src/framelab/protocol/messages.py      make_response/make_error/make_event
src/framelab/protocol/tsgen.py         TypedDict → TypeScript generator
src/framelab/transport/dispatcher.py   Dispatcher, Reply, ProtocolMismatch
src/framelab/transport/server.py       FramelabServer (Starlette + uvicorn thread, token/Host/Origin)
src/framelab/transport/widget.py       FramelabWidget (anywidget)
src/framelab/launch/__init__.py        open_window(), default_order()
src/framelab/launch/browsers.py        find_chromium()
src/framelab/launch/chromium.py        build_command(), launch_app_window(), ChromiumWindow
src/framelab/launch/webview.py         pywebview_available(), run_pywebview()
src/framelab/launch/browser.py         open_in_browser()
tools/gen_ts_types.py                  CLI: writes frontend/src/generated/protocol.ts
frontend/…                             Vite + React skeleton (see Task 9)
tests/…                                pytest suites per module
spikes/…                               throwaway spikes (deleted at M0 close)
docs/superpowers/spikes/2026-09-23-m0-spikes.md   consolidated spike results (kept)
.github/workflows/ci.yml               CI skeleton
```

---

### Task 1: Python package skeleton and dev environment

**Files:**
- Create: `pyproject.toml`, `src/framelab/__init__.py`, `tests/test_package.py`

**Interfaces:**
- Produces: installable `framelab` package (editable) with `framelab.__version__ == "0.0.1.dev0"`; pytest + ruff configured; marker `slow`.

- [ ] **Step 1: Write `pyproject.toml`** (no build hook yet — added in Task 10)

```toml
[build-system]
requires = ["hatchling>=1.32"]
build-backend = "hatchling.build"

[project]
name = "framelab"
dynamic = ["version"]
description = "Explore, transform and plot pandas DataFrames without writing code — always with the exact Python code."
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
authors = [{ name = "Emiliano Tejada", email = "emitejadaaragon@gmail.com" }]
requires-python = ">=3.11"
keywords = ["pandas", "matplotlib", "dataframe", "gui", "no-code", "jupyter", "eda"]
classifiers = [
  "Development Status :: 2 - Pre-Alpha",
  "Intended Audience :: Science/Research",
  "Intended Audience :: Education",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Python :: 3.14",
  "Framework :: Jupyter",
  "Topic :: Scientific/Engineering :: Visualization",
]
dependencies = [
  "pandas>=3.0,<4",
  "matplotlib>=3.11,<4",
  "numpy>=1.26",
  "pyarrow>=13",
  "anywidget>=0.11",
  "starlette>=0.40",
  "uvicorn>=0.30",
  "websockets>=13",
  "varname[all]>=1.0",
  "psutil>=5.9",
  "platformdirs>=4",
]

[project.optional-dependencies]
desktop = ["pywebview>=6.2"]
io = ["openpyxl", "tabulate", "jinja2", "lxml"]

[project.urls]
Repository = "https://github.com/emitejadaa/framelab"

[dependency-groups]
dev = [
  "pytest>=8",
  "pytest-timeout",
  "hypothesis",
  "ruff",
  "httpx",
  "numpydoc",
  "nbformat",
  "nbclient",
  "ipykernel",
  "jupyterlab",
  "build",
]

[tool.hatch.version]
path = "src/framelab/__init__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/framelab"]
artifacts = ["src/framelab/_static/*"]

[tool.hatch.build.targets.sdist]
include = ["src/framelab", "frontend", "tools", "tests", "hatch_build.py", "README.md", "LICENSE", "mise.toml"]
exclude = ["frontend/node_modules", "frontend/dist", "frontend/tests/scaffold"]
artifacts = ["src/framelab/_static/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
timeout = 120
markers = ["slow: builds packages, launches browsers or kernels"]

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests", "tools"]
extend-exclude = ["spikes"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
```

- [ ] **Step 2: Write `src/framelab/__init__.py`**

```python
"""framelab — explore, transform and plot pandas DataFrames without writing code."""

__version__ = "0.0.1.dev0"
```

- [ ] **Step 3: Write the failing test `tests/test_package.py`**

```python
import framelab


def test_version_is_pep440_dev_string():
    assert framelab.__version__ == "0.0.1.dev0"
```

- [ ] **Step 4: Install editable + dev group and run**

Run: `.venv/bin/pip install -e . --group dev -q && .venv/bin/python -m pytest tests/test_package.py -v`
Expected: PASS (1 passed). `.venv/bin/ruff check . && .venv/bin/ruff format --check .` → no errors.

- [ ] **Step 5: Commit** — `git add pyproject.toml src tests && git commit` ("Add Python package skeleton, dev tooling and pytest/ruff config").

---

### Task 2: Throwaway spikes batch A (Python-side + standalone frontend spikes)

Runs **in parallel with Tasks 3–9** (independent directories). Each spike lives in `spikes/<id>/`, writes `spikes/<id>/RESULT.md` with: numbers measured, PASS/FAIL per criterion, and the **decision** it implies for the plan. Spike agents never run git and never modify files outside their `spikes/<id>/` directory (installing extra Python interpreters with mise is allowed).

| id | What to do | Pass criteria → decision |
|---|---|---|
| **s5-mpl-render** | Script with `matplotlib.figure.Figure` + `FigureCanvasAgg` (no pyplot). For line, scatter (uniform + colour-mapped), hist, hexbin, boxplot at 100k / 1M / 5M points: time build+draw with and without M4 decimation (numpy `reduceat` min/max per pixel column), PNG encode from `buffer_rgba()` via Pillow `compress_level=1` at dpr 1 and 2, PNG size, SVG/PDF export time/size at 1M, `matplotlib.style.context` overhead. Check that `plt.figure(fig)` + `fig.savefig` work for a `Figure()` created outside pyplot (run in a subprocess that imports pyplot). | Preview round trip ≤150 ms at a chosen sampling threshold; PNG ≤400 KB at dpr 2 → record the sampling threshold (points) to use as default. `plt.figure(fig)` works → `res.figures` returns plain Figures. |
| **s6-pandas-census** | Prototype introspection over DataFrame, Series, DataFrameGroupBy, SeriesGroupBy, Resampler, Rolling, Expanding, ExponentialMovingWindow, Index, `.str`, `.dt`, `.cat` (on real dtypes via `head(0)`). Classify members with `inspect.getattr_static` (method/property/Accessor/classmethod). For every public method parameter, try: `inspect.signature` default + annotation string resolved against `pandas._typing` (eval with `vars(pandas._typing)`), else `numpydoc.docscrape.NumpyDocString` type line. Count params that map to a concrete widget (enum/bool/int/float/str/column/columns/label/dict/dtype/other-df/func). List members returning non-pandas objects or mutating (`update`, `insert`, `pop`, `info`, `style`, `plot`, `iter*`). | Report % of parameters with a concrete widget per class; ≥80 % overall → auto-forms viable as planned; list of parameter names needing overrides (seed for the ~60-method override table). |
| **s7-arrow-robust** | Build messy DataFrames: mixed-type object columns, duplicate column names, int / tuple / Timestamp column labels, MultiIndex rows+columns, Period, Interval, tz-aware datetimes, categorical with non-string categories, nullable Int64/Float64/boolean with `pd.NA`, Decimal, list/dict cells, pandas 3 `str` dtype, 5M×30 numeric. Convert windows (`slice(offset, 1000)`) to Arrow IPC stream bytes with positional field names `c0…cN` and a JSON label list; per-column fallback to string (+ badge flag) when pyarrow fails. Write the `.arrow` files and decode them in Node with `@uwdata/flechette` (`tableFromIPC`) in `spikes/s7-arrow-robust/js/`. | Every column displayable (native or string fallback); 1000×50 window encode <20 ms (Python) and decode <10 ms (Node). |
| **s8-varname-env** | Install Python 3.11, 3.12, 3.13 with mise (`mise install python@3.11 …`, outside the repo). On 3.11–3.14 test caller-name detection via `executing.Source.executing(frame).node` + `ast.unparse` and the identity-scan fallback, for: script file, `python -c`, stdin script, REPL (`python -i` fed via stdin), IPython terminal, Jupyter kernel (nbclient), a wrapper function, `f(dfs[0])`, multi-line call, kwargs. Also print what `framelab.env.detect_env` (copy the Task 4 logic into the spike) returns in each. | Correct name or graceful fallback everywhere, never raising → confirms `naming.py` design (Task 5) or lists required changes. |
| **s11-copy-memory** | pandas 3.0.6, 3M×20 mixed frame: measure RSS delta and time for `v.copy()`, `v.copy(deep=False)`, `v2 = v.copy(); v2["c"] = …`, `v.assign(c=…)`, `v.copy(deep=False)` + assignment; confirm results equal and original untouched. | Confirms (or refutes) "`copy()` is eager, `copy(deep=False)` + assign is lazy and safe" → the executed-form rule of the spec. |
| **s1-glide** | Standalone Vite React 19.3 app in `spikes/s1-glide/` with `@glideapps/glide-data-grid@6.0.4-alpha24` (exact) + its peers. 5M rows × 30 cols synthetic `getCellContent` (deterministic from row/col), `drawHeader` drawing a 20-bin mini histogram, `onHeaderContextMenu`/`onCellContextMenu` opening a menu rendered into a portal element inside a `.fl-root` wrapper, overlay editor portal inside `.fl-root`. Build it, serve `dist/` with `python -m http.server`, open it in Chromium via the chrome-devtools MCP (new page), record a performance trace while scrolling from top to row 4 999 000, capture console messages. Also mount two grids on one page. | No long task >50 ms during scroll; zero React-19 console errors; last row reachable → keep Glide (else switch the table plan to AG Grid Community Infinite Row Model). |
| **s10-dnd-reactflow** | Standalone Vite app in `spikes/s10-dnd-reactflow/` with `@xyflow/react@12.11.6`: 6 nodes, pan/zoom; (a) normal node drag inside canvas; (b) dragging a node and releasing over two drop boxes rendered **outside** the canvas (and over a fake tab bar) detected in `onNodeDragStop` by DOMRect hit-testing, node snapped back to its start position; (c) dropping a node on another node detected with `getIntersectingNodes`; (d) custom pointer-events drag (setPointerCapture + ghost in a portal) from a sidebar list into the canvas using `screenToFlowPosition`. Verify each with the chrome-devtools MCP `drag` tool + `evaluate_script` reading an on-page event log. | (a)–(d) all work at zoom 0.5 and 2 → confirms the DnD split of the spec (React Flow drag for canvas nodes, custom pointer DnD only for external sources). |

- [ ] **Step 1:** Launch the spikes above (parallel workflow, one agent per spike) with the exact briefs.
- [ ] **Step 2:** Read every `RESULT.md`; copy the numbers and decisions into `docs/superpowers/spikes/2026-09-23-m0-spikes.md` (created in Task 16).
- [ ] **Step 3:** If any spike FAILS, update the spec section it affects before starting the milestone that depends on it (M3 for s1, M5 for s5, M1b/M4 for s6, M2a for s10, M1a for s11).

---

### Task 3: Options registry (`fl.options`)

**Files:**
- Create: `src/framelab/options.py`, `tests/test_options.py`
- Modify: `src/framelab/__init__.py`

**Interfaces:**
- Produces: `Option(key, default, type, choices=None)` (properties `category`, `i18n_key`, method `validate(value)`), `OptionError(ValueError)`, `OptionsRegistry` (`register`, `definition`, `get`, `set`, `reset`, `keys`, `has_prefix`, `describe() -> list[dict]`, `subscribe(listener) -> unsubscribe`), `OptionsNamespace(registry, prefix="")`, `build_default_registry()`, module globals `registry`, `options`, `get_option`, `set_option`, `reset_option`. `describe()` items: `{"key","category","value","default","type","i18n_key", "choices"?}`.

- [ ] **Step 1: Write failing tests `tests/test_options.py`**

```python
import pytest

from framelab.options import Option, OptionError, OptionsNamespace, build_default_registry


@pytest.fixture
def reg():
    return build_default_registry()


def test_defaults(reg):
    assert reg.get("general.theme") == "system"
    assert reg.get("general.accent") == "#3B82F6"
    assert reg.get("code.style") == "steps"


def test_set_and_reset(reg):
    reg.set("general.theme", "dark")
    assert reg.get("general.theme") == "dark"
    reg.reset("general.theme")
    assert reg.get("general.theme") == "system"


def test_rejects_value_outside_choices(reg):
    with pytest.raises(OptionError, match="general.theme"):
        reg.set("general.theme", "purple")


def test_rejects_wrong_type_and_bool_as_int(reg):
    with pytest.raises(OptionError):
        reg.set("general.inline_height", "720")
    with pytest.raises(OptionError):
        reg.set("general.inline_height", True)
    reg.set("general.inline_height", 800)
    assert reg.get("general.inline_height") == 800


def test_unknown_key(reg):
    with pytest.raises(KeyError):
        reg.get("nope.nothing")


def test_duplicate_registration(reg):
    with pytest.raises(ValueError):
        reg.register(Option("general.theme", "system", str, ("system",)))


def test_invalid_default_is_rejected():
    reg = build_default_registry()
    with pytest.raises(OptionError):
        reg.register(Option("x.y", 3, str))


def test_namespace_attribute_access(reg):
    ns = OptionsNamespace(reg)
    assert ns.general.theme == "system"
    ns.general.theme = "light"
    assert reg.get("general.theme") == "light"
    assert "theme" in dir(ns.general)
    with pytest.raises(AttributeError):
        ns.general.nothing  # noqa: B018
    with pytest.raises(AttributeError):
        ns.general.nothing = 1


def test_namespace_repr_lists_values(reg):
    text = repr(OptionsNamespace(reg).code)
    assert 'code.style = "steps"' in text or "code.style = 'steps'" in text


def test_describe_shape(reg):
    items = {d["key"]: d for d in reg.describe()}
    theme = items["general.theme"]
    assert theme == {
        "key": "general.theme",
        "category": "general",
        "value": "system",
        "default": "system",
        "type": "str",
        "i18n_key": "prefs.general.theme",
        "choices": ["system", "light", "dark"],
    }
    assert "choices" not in items["general.accent"]


def test_subscribe_notifies_and_unsubscribes(reg):
    seen = []
    off = reg.subscribe(lambda k, v: seen.append((k, v)))
    reg.set("general.theme", "dark")
    reg.reset("general.theme")
    off()
    reg.set("general.theme", "light")
    assert seen == [("general.theme", "dark"), ("general.theme", "system")]


def test_module_level_helpers():
    import framelab

    framelab.set_option("general.theme", "dark")
    try:
        assert framelab.get_option("general.theme") == "dark"
        assert framelab.options.general.theme == "dark"
    finally:
        framelab.reset_option("general.theme")
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_options.py -v` → FAIL (`ModuleNotFoundError: framelab.options`).

- [ ] **Step 3: Implement `src/framelab/options.py`**

```python
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

    def keys(self) -> list[str]:
        return sorted(self._defs)

    def has_prefix(self, prefix: str) -> bool:
        return any(k.startswith(prefix + ".") for k in self._defs)

    def describe(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for key in self.keys():
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
            {k[len(prefix) :].split(".", 1)[0] for k in self._registry.keys() if k.startswith(prefix)}
        )

    def __repr__(self) -> str:
        prefix = f"{self._prefix}." if self._prefix else ""
        keys = [k for k in self._registry.keys() if k.startswith(prefix)]
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
```

Update `src/framelab/__init__.py`:

```python
"""framelab — explore, transform and plot pandas DataFrames without writing code."""

from .options import get_option, options, reset_option, set_option

__version__ = "0.0.1.dev0"

__all__ = ["__version__", "get_option", "options", "reset_option", "set_option"]
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_options.py -v` → all PASS. `ruff check` clean.
- [ ] **Step 5: Commit** ("Add options registry exposed as fl.options").

---

### Task 4: Environment detection and mode resolution

**Files:**
- Create: `src/framelab/env.py`, `tests/test_env.py`

**Interfaces:**
- Produces: `Env` (str Enum: `SCRIPT, REPL, IPYTHON_TERMINAL, JUPYTER, VSCODE, COLAB, MARIMO, NO_WIDGETS`), `INLINE_ENVS`, `detect_env(*, modules=None, environ=None, ipython=<missing>, interactive=None) -> Env`, `resolve_mode(requested: str, env: Env) -> Literal["inline","window"]`.

- [ ] **Step 1: Write failing tests `tests/test_env.py`**

```python
import types

import pytest

from framelab.env import Env, detect_env, resolve_mode


def shell(name):
    return type(name, (), {})()


def test_plain_script():
    assert detect_env(modules={}, environ={}, ipython=None, interactive=False) is Env.SCRIPT


def test_plain_repl():
    assert detect_env(modules={}, environ={}, ipython=None, interactive=True) is Env.REPL


def test_jupyter_kernel():
    assert detect_env(modules={}, environ={}, ipython=shell("ZMQInteractiveShell")) is Env.JUPYTER


def test_vscode_kernel():
    env = detect_env(modules={}, environ={"VSCODE_PID": "1"}, ipython=shell("ZMQInteractiveShell"))
    assert env is Env.VSCODE


def test_colab():
    mods = {"google.colab": types.ModuleType("google.colab")}
    assert detect_env(modules=mods, environ={}, ipython=shell("Shell")) is Env.COLAB


def test_spyder_kernel_has_no_widgets():
    mods = {"spyder_kernels": types.ModuleType("spyder_kernels")}
    env = detect_env(modules=mods, environ={}, ipython=shell("ZMQInteractiveShell"))
    assert env is Env.NO_WIDGETS


def test_ipython_terminal():
    env = detect_env(modules={}, environ={}, ipython=shell("TerminalInteractiveShell"))
    assert env is Env.IPYTHON_TERMINAL


def test_marimo():
    mo = types.ModuleType("marimo")
    mo.running_in_notebook = lambda: True
    assert detect_env(modules={"marimo": mo}, environ={}, ipython=None) is Env.MARIMO


def test_marimo_imported_but_not_running():
    mo = types.ModuleType("marimo")
    mo.running_in_notebook = lambda: False
    env = detect_env(modules={"marimo": mo}, environ={}, ipython=None, interactive=False)
    assert env is Env.SCRIPT


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        (Env.SCRIPT, "window"),
        (Env.REPL, "window"),
        (Env.IPYTHON_TERMINAL, "window"),
        (Env.NO_WIDGETS, "window"),
        (Env.JUPYTER, "inline"),
        (Env.VSCODE, "inline"),
        (Env.COLAB, "inline"),
        (Env.MARIMO, "inline"),
    ],
)
def test_auto_mode(env, expected):
    assert resolve_mode("auto", env) == expected


def test_explicit_modes():
    assert resolve_mode("window", Env.JUPYTER) == "window"
    assert resolve_mode("inline", Env.JUPYTER) == "inline"
    with pytest.raises(ValueError, match="inline"):
        resolve_mode("inline", Env.SCRIPT)
    with pytest.raises(ValueError, match="mode"):
        resolve_mode("popup", Env.SCRIPT)
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_env.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement `src/framelab/env.py`**

```python
"""Detect where framelab runs and decide whether the UI is shown inline or in a window."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from enum import Enum
from typing import Any, Literal

__all__ = ["INLINE_ENVS", "Env", "Mode", "detect_env", "resolve_mode"]

Mode = Literal["inline", "window"]
_MISSING: Any = object()


class Env(str, Enum):
    SCRIPT = "script"
    REPL = "repl"
    IPYTHON_TERMINAL = "ipython-terminal"
    JUPYTER = "jupyter"
    VSCODE = "vscode"
    COLAB = "colab"
    MARIMO = "marimo"
    NO_WIDGETS = "no-widgets"


INLINE_ENVS = frozenset({Env.JUPYTER, Env.VSCODE, Env.COLAB, Env.MARIMO})


def _current_ipython(modules: Mapping[str, Any]) -> Any:
    ipy = modules.get("IPython")
    if ipy is None:
        return None
    try:
        return ipy.get_ipython()
    except Exception:
        return None


def _marimo_running(modules: Mapping[str, Any]) -> bool:
    mo = modules.get("marimo")
    if mo is None:
        return False
    try:
        return bool(mo.running_in_notebook())
    except Exception:
        return False


def detect_env(
    *,
    modules: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    ipython: Any = _MISSING,
    interactive: bool | None = None,
) -> Env:
    modules = sys.modules if modules is None else modules
    environ = os.environ if environ is None else environ
    if _marimo_running(modules):
        return Env.MARIMO
    shell = _current_ipython(modules) if ipython is _MISSING else ipython
    if shell is not None:
        name = type(shell).__name__
        if "google.colab" in modules:
            return Env.COLAB
        if "spyder_kernels" in modules or "PYCHARM_HOSTED" in environ:
            return Env.NO_WIDGETS
        if name == "ZMQInteractiveShell":
            return Env.VSCODE if "VSCODE_PID" in environ else Env.JUPYTER
        if name == "TerminalInteractiveShell":
            return Env.IPYTHON_TERMINAL
        return Env.NO_WIDGETS
    if interactive is None:
        interactive = hasattr(sys, "ps1") or bool(sys.flags.interactive)
    return Env.REPL if interactive else Env.SCRIPT


def resolve_mode(requested: str, env: Env) -> Mode:
    if requested == "auto":
        return "inline" if env in INLINE_ENVS else "window"
    if requested == "inline":
        if env not in INLINE_ENVS:
            raise ValueError(
                "mode='inline' needs Jupyter, VS Code, Colab or marimo; use mode='window' here"
            )
        return "inline"
    if requested == "window":
        return "window"
    raise ValueError(f"mode must be 'auto', 'inline' or 'window', not {requested!r}")
```

- [ ] **Step 4: Run** tests → PASS.
- [ ] **Step 5: Commit** ("Add environment detection and inline/window mode resolution").

---

### Task 5: Root naming (caller variable names)

**Files:**
- Create: `src/framelab/naming.py`, `tests/test_naming.py`

**Interfaces:**
- Produces: `RootSpec(name: str, obj: Any, source_expr: str | None)` (frozen dataclass), `DEFAULT_ROOT_NAME = "df"`, `RESERVED_NAMES`, `sanitize_identifier(text, fallback="df") -> str`, `unique_name(base, taken) -> str`, `scan_frame_for(obj, frame) -> list[str]`, `resolve_root_names(args, kwargs, frame, explicit_name=None) -> list[RootSpec]`. `source_expr` is the user's expression when it differs from `name` (e.g. `"dfs[0]"` for name `dfs_0`, `"df"` for `explore(ventas=df)`), else `None`.

- [ ] **Step 1: Write failing tests `tests/test_naming.py`**

```python
import sys

import pandas as pd
import pytest

from framelab.naming import (
    RootSpec,
    resolve_root_names,
    sanitize_identifier,
    scan_frame_for,
    unique_name,
)


def fake_explore(*args, name=None, **kwargs):
    return resolve_root_names(args, kwargs, sys._getframe(1), explicit_name=name)


@pytest.fixture
def ventas():
    return pd.DataFrame({"a": [1, 2]})


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ventas", "ventas"),
        ("ventas 2024-01", "ventas_2024_01"),
        ("2024", "df_2024"),
        ("class", "df_class"),
        ("pd", "df_pd"),
        ("list", "df_list"),
        ("año", "año"),
        ("", "df"),
        ("---", "df"),
    ],
)
def test_sanitize_identifier(text, expected):
    assert sanitize_identifier(text) == expected


def test_unique_name():
    assert unique_name("x", set()) == "x"
    assert unique_name("x", {"x"}) == "x_2"
    assert unique_name("x", {"x", "x_2"}) == "x_3"


def test_single_variable(ventas):
    specs = fake_explore(ventas)
    assert specs == [RootSpec("ventas", ventas, None)]


def test_two_variables(ventas):
    clientes = pd.DataFrame({"b": [1]})
    specs = fake_explore(ventas, clientes)
    assert [s.name for s in specs] == ["ventas", "clientes"]


def test_multiline_call(ventas):
    specs = fake_explore(
        ventas,
    )
    assert specs[0].name == "ventas"


def test_subscript_expression(ventas):
    dfs = [ventas]
    specs = fake_explore(dfs[0])
    assert specs[0].name == "dfs_0"
    assert specs[0].source_expr == "dfs[0]"


def test_call_expression_falls_back_to_df():
    specs = fake_explore(pd.DataFrame({"a": [1]}))
    assert specs[0].name == "df"
    assert specs[0].source_expr is None


def test_keyword_names(ventas):
    df = ventas
    specs = fake_explore(sales=df)
    assert specs == [RootSpec("sales", ventas, "df")]


def test_explicit_name(ventas):
    specs = fake_explore(ventas, name="mis ventas")
    assert specs[0].name == "mis_ventas"


def test_explicit_name_needs_single_positional(ventas):
    with pytest.raises(ValueError, match="name="):
        fake_explore(ventas, ventas, name="x")


def test_same_object_twice_is_deduplicated(ventas):
    specs = fake_explore(ventas, ventas)
    assert [(s.name, s.source_expr) for s in specs] == [("ventas", None), ("ventas_2", "ventas")]


def test_no_source_uses_identity_scan(ventas):
    ns = {"fake_explore": fake_explore, "ventas_sin_fuente": ventas}
    exec("result = fake_explore(ventas_sin_fuente)", ns)
    assert ns["result"][0].name == "ventas_sin_fuente"


def test_identity_scan_skips_ipython_noise(ventas):
    frame = type("F", (), {"f_locals": {"_": ventas, "_3": ventas, "Out": {}}, "f_globals": {"x": ventas}})()
    assert scan_frame_for(ventas, frame) == ["x"]


def test_nothing_found_defaults_to_df(ventas):
    ns = {"fake_explore": fake_explore, "pd": pd}
    exec("result = fake_explore(pd.DataFrame({'a': [1]}))", ns)
    assert ns["result"][0].name == "df"
```

- [ ] **Step 2: Run** → FAIL (module missing).

- [ ] **Step 3: Implement `src/framelab/naming.py`**

```python
"""Names of root DataFrames: detect the caller's variable names, sanitize and de-duplicate."""

from __future__ import annotations

import ast
import builtins
import keyword
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DEFAULT_ROOT_NAME",
    "RESERVED_NAMES",
    "RootSpec",
    "resolve_root_names",
    "sanitize_identifier",
    "scan_frame_for",
    "unique_name",
]

DEFAULT_ROOT_NAME = "df"
RESERVED_NAMES = frozenset({"pd", "np", "plt", "mpl", "fl"}) | frozenset(dir(builtins))
_IPYTHON_NOISE = re.compile(r"^(_+|_\d+|_i+\d*|In|Out|_oh|_dh|_ih|exit|quit|get_ipython)$")


@dataclass(frozen=True)
class RootSpec:
    name: str
    obj: Any
    source_expr: str | None


def sanitize_identifier(text: str, fallback: str = DEFAULT_ROOT_NAME) -> str:
    s = re.sub(r"\W+", "_", text.strip()).strip("_")
    if not s:
        return fallback
    if s[0].isdigit() or keyword.iskeyword(s) or s in RESERVED_NAMES:
        s = f"df_{s}"
    return s


def unique_name(base: str, taken: Iterable[str]) -> str:
    taken = set(taken)
    if base not in taken:
        return base
    i = 2
    while f"{base}_{i}" in taken:
        i += 1
    return f"{base}_{i}"


def scan_frame_for(obj: Any, frame: Any) -> list[str]:
    names: list[str] = []
    for scope in (frame.f_locals, frame.f_globals):
        for key, value in list(scope.items()):
            if value is obj and not _IPYTHON_NOISE.match(key) and key not in names:
                names.append(key)
    return names


def _call_node(frame: Any) -> ast.Call | None:
    try:
        import executing

        node = executing.Source.executing(frame).node
    except Exception:
        return None
    return node if isinstance(node, ast.Call) else None


def _is_simple_access(expr: ast.expr) -> bool:
    while isinstance(expr, (ast.Attribute, ast.Subscript)):
        if isinstance(expr, ast.Subscript) and not isinstance(expr.slice, (ast.Constant, ast.Name)):
            return False
        expr = expr.value
    return isinstance(expr, ast.Name)


def _name_for_expr(expr: ast.expr) -> tuple[str, str | None]:
    if isinstance(expr, ast.Name):
        return expr.id, None
    if _is_simple_access(expr):
        text = ast.unparse(expr)
        return sanitize_identifier(text), text
    return DEFAULT_ROOT_NAME, None


def resolve_root_names(
    args: Sequence[Any],
    kwargs: Mapping[str, Any],
    frame: Any,
    explicit_name: str | None = None,
) -> list[RootSpec]:
    if explicit_name is not None and len(args) != 1:
        raise ValueError("name= can only be used with exactly one positional DataFrame")
    call = _call_node(frame) if frame is not None else None
    positional: list[ast.expr] | None = None
    keyword_exprs: dict[str, ast.expr] = {}
    if call is not None and not any(isinstance(a, ast.Starred) for a in call.args):
        if len(call.args) == len(args):
            positional = list(call.args)
        keyword_exprs = {k.arg: k.value for k in call.keywords if k.arg is not None}

    raw: list[tuple[str, Any, str | None]] = []
    for i, obj in enumerate(args):
        if explicit_name is not None:
            raw.append((sanitize_identifier(explicit_name), obj, None))
        elif positional is not None:
            name, src = _name_for_expr(positional[i])
            raw.append((name, obj, src))
        else:
            found = scan_frame_for(obj, frame) if frame is not None else []
            raw.append((found[0] if found else DEFAULT_ROOT_NAME, obj, None))
    for key, obj in kwargs.items():
        expr = keyword_exprs.get(key)
        src = None
        if expr is not None and not (isinstance(expr, ast.Name) and expr.id == key):
            src = ast.unparse(expr) if _is_simple_access(expr) else None
        raw.append((sanitize_identifier(key), obj, src))

    taken: set[str] = set()
    out: list[RootSpec] = []
    for name, obj, src in raw:
        final = unique_name(name, taken)
        taken.add(final)
        if final != name and src is None and name != DEFAULT_ROOT_NAME:
            src = name
        out.append(RootSpec(final, obj, src))
    return out
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_naming.py -v` → PASS. If the executing-based tests fail under pytest assertion rewriting, keep the calls outside `assert` statements (as written) and re-run; if still failing, add `-p no:cacheprovider` is NOT the fix — instead inspect `executing.Source.executing(frame).node` in a debug print and adjust `_call_node`.
- [ ] **Step 5: Commit** ("Detect root DataFrame names from the caller's code").

---

### Task 6: Protocol schema, codec and TypeScript generation

**Files:**
- Create: `src/framelab/protocol/__init__.py`, `schema.py`, `codec.py`, `messages.py`, `tsgen.py`, `tools/gen_ts_types.py`, `tests/test_protocol.py`, `tests/test_tsgen.py`
- Create (generated): `frontend/src/generated/protocol.ts`

**Interfaces:**
- Produces: `PROTOCOL_VERSION = 1`; TypedDicts `ErrorInfo`, `Envelope`, `HelloParams`, `HelloResult`, `RootSummary`, `OptionDescription`, `SessionSnapshot`; Literal alias `MessageType`, `RootKind`; `encode_frame(env, buffers=()) -> bytes | str`, `decode_frame(data) -> (Envelope, list[bytes])`, `ProtocolError`, `dumps(obj) -> str`; `make_response(id, result)`, `make_error(id, code, message, traceback=None)`, `make_event(method, params, rev=None)`; `tsgen.render_module(module) -> str`.
- Binary frame layout (shared with TS `codec.ts`): `uint32 big-endian header length N` + `N bytes UTF-8 JSON envelope` (with `"buffers": [len0, len1, …]`) + concatenated buffers. Frames without buffers are plain JSON text.

- [ ] **Step 1: Write failing tests `tests/test_protocol.py`**

```python
import json

import numpy as np
import pytest

from framelab.protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    decode_frame,
    dumps,
    encode_frame,
    make_error,
    make_event,
    make_response,
)


def req(**extra):
    return {"v": PROTOCOL_VERSION, "id": "c1", "type": "req", "method": "app.ping", **extra}


def test_text_roundtrip():
    frame = encode_frame(req(params={"a": 1}))
    assert isinstance(frame, str)
    env, bufs = decode_frame(frame)
    assert env["params"] == {"a": 1}
    assert bufs == []


def test_binary_roundtrip_with_buffers():
    frame = encode_frame(req(), [b"abc", b"", bytes(range(10))])
    assert isinstance(frame, bytes)
    env, bufs = decode_frame(frame)
    assert bufs == [b"abc", b"", bytes(range(10))]
    assert env["buffers"] == [3, 0, 10]


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        json.dumps([1, 2]),
        json.dumps({"v": 99, "id": "x", "type": "req", "method": "m"}),
        json.dumps({"v": PROTOCOL_VERSION, "id": "x", "type": "nope"}),
        json.dumps({"v": PROTOCOL_VERSION, "id": "x", "type": "req"}),
        json.dumps({"v": PROTOCOL_VERSION, "type": "res"}),
        b"\x00\x00",
    ],
)
def test_rejects_bad_frames(bad):
    with pytest.raises(ProtocolError):
        decode_frame(bad)


def test_rejects_mismatched_buffer_lengths():
    frame = bytearray(encode_frame(req(), [b"abcd"]))
    with pytest.raises(ProtocolError):
        decode_frame(bytes(frame[:-1]))


def test_dumps_numpy_scalars_and_rejects_nan():
    assert json.loads(dumps({"a": np.int64(3), "b": np.float32(1.5), "c": np.bool_(True)})) == {
        "a": 3,
        "b": 1.5,
        "c": True,
    }
    with pytest.raises(ValueError):
        dumps({"x": float("nan")})


def test_message_builders():
    assert make_response("c1", {"ok": 1}) == {
        "v": PROTOCOL_VERSION,
        "id": "c1",
        "type": "res",
        "result": {"ok": 1},
    }
    err = make_error("c2", "internal", "boom", "Traceback…")
    assert err["error"] == {
        "code": "internal",
        "i18n_key": "errors.internal",
        "message": "boom",
        "traceback": "Traceback…",
    }
    assert "traceback" not in make_error("c3", "bad_request", "x")["error"]
    evt = make_event("node.state", {"id": "n1"}, rev=4)
    assert evt == {"v": PROTOCOL_VERSION, "type": "evt", "method": "node.state", "params": {"id": "n1"}, "rev": 4}
```

`tests/test_tsgen.py`:

```python
import sys
import types
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from framelab.protocol import schema
from framelab.protocol.tsgen import render_module

ROOT = Path(__file__).resolve().parents[1]


def test_render_small_module():
    mod = types.ModuleType("fake_schema")
    Color = Literal["red", "blue"]

    class Item(TypedDict):
        name: str
        size: int
        tags: list[str]
        color: Color
        meta: dict[str, Any]
        note: NotRequired[str | None]

    Item.__module__ = "fake_schema"
    mod.LIMIT = 3
    mod.Color = Color
    mod.Item = Item
    sys.modules["fake_schema"] = mod
    try:
        out = render_module(mod)
    finally:
        del sys.modules["fake_schema"]
    assert "export const LIMIT = 3 as const;" in out
    assert 'export type Color = "red" | "blue";' in out
    assert "export interface Item {" in out
    assert "  name: string;" in out
    assert "  size: number;" in out
    assert "  tags: string[];" in out
    assert "  color: Color;" in out
    assert "  meta: Record<string, unknown>;" in out
    assert "  note?: string | null;" in out


def test_generated_file_is_up_to_date():
    generated = (ROOT / "frontend/src/generated/protocol.ts").read_text(encoding="utf-8")
    assert generated == render_module(schema), "run: .venv/bin/python tools/gen_ts_types.py"
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_protocol.py tests/test_tsgen.py -v` → FAIL (modules missing).

- [ ] **Step 3: Implement the protocol package**

`src/framelab/protocol/schema.py`:

```python
"""Wire-level types shared by Python and the frontend (TypeScript is generated from here)."""

from typing import Any, Literal, NotRequired, TypedDict

PROTOCOL_VERSION = 1

MessageType = Literal["req", "res", "evt", "cancel"]
RootKind = Literal["DataFrame", "Series"]


class ErrorInfo(TypedDict):
    code: str
    i18n_key: str
    message: str
    traceback: NotRequired[str]


class Envelope(TypedDict):
    v: int
    type: MessageType
    id: NotRequired[str]
    method: NotRequired[str]
    params: NotRequired[dict[str, Any]]
    result: NotRequired[Any]
    error: NotRequired[ErrorInfo]
    buffers: NotRequired[list[int]]
    rev: NotRequired[int]


class HelloParams(TypedDict):
    protocol_version: int
    client: str


class HelloResult(TypedDict):
    protocol_version: int
    framelab_version: str
    session_id: str


class RootSummary(TypedDict):
    id: str
    name: str
    kind: RootKind
    shape: list[int]


class OptionDescription(TypedDict):
    key: str
    category: str
    value: Any
    default: Any
    type: str
    i18n_key: str
    choices: NotRequired[list[Any]]


class SessionSnapshot(TypedDict):
    rev: int
    session_id: str
    roots: list[RootSummary]
    options: list[OptionDescription]
```

`src/framelab/protocol/codec.py`:

```python
"""Frames: JSON text, or binary = uint32 BE header length + JSON header + raw buffers."""

from __future__ import annotations

import json
import struct
from collections.abc import Iterable
from typing import Any

import numpy as np

from .schema import PROTOCOL_VERSION, Envelope

__all__ = ["ProtocolError", "decode_frame", "dumps", "encode_frame", "validate_envelope"]

_HEADER = struct.Struct(">I")
_VALID_TYPES = frozenset({"req", "res", "evt", "cancel"})


class ProtocolError(ValueError):
    """A frame or envelope does not follow the framelab protocol."""


def _default(obj: Any) -> Any:
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    raise TypeError(f"{type(obj).__name__} is not JSON serializable")


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=_default, allow_nan=False, ensure_ascii=False, separators=(",", ":"))


def validate_envelope(obj: Any) -> Envelope:
    if not isinstance(obj, dict):
        raise ProtocolError("envelope must be a JSON object")
    if obj.get("v") != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version {obj.get('v')!r}")
    kind = obj.get("type")
    if kind not in _VALID_TYPES:
        raise ProtocolError(f"invalid message type {kind!r}")
    if kind in ("req", "evt") and not isinstance(obj.get("method"), str):
        raise ProtocolError(f"{kind} message without method")
    if kind in ("req", "res", "cancel") and not isinstance(obj.get("id"), str):
        raise ProtocolError(f"{kind} message without id")
    return obj  # type: ignore[return-value]


def encode_frame(envelope: Envelope | dict[str, Any], buffers: Iterable[bytes] = ()) -> bytes | str:
    bufs = [bytes(b) for b in buffers]
    if not bufs:
        return dumps(envelope)
    header = dumps({**envelope, "buffers": [len(b) for b in bufs]}).encode("utf-8")
    return b"".join([_HEADER.pack(len(header)), header, *bufs])


def decode_frame(data: bytes | str) -> tuple[Envelope, list[bytes]]:
    if isinstance(data, str):
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid JSON: {exc}") from None
        return validate_envelope(obj), []
    if len(data) < _HEADER.size:
        raise ProtocolError("frame too short")
    (n,) = _HEADER.unpack_from(data, 0)
    end = _HEADER.size + n
    if end > len(data):
        raise ProtocolError("truncated header")
    try:
        obj = json.loads(data[_HEADER.size : end])
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError(f"invalid JSON header: {exc}") from None
    env = validate_envelope(obj)
    lengths = env.get("buffers", [])
    if not isinstance(lengths, list) or not all(isinstance(x, int) and x >= 0 for x in lengths):
        raise ProtocolError("invalid buffer lengths")
    out: list[bytes] = []
    offset = end
    for length in lengths:
        out.append(bytes(data[offset : offset + length]))
        offset += length
    if offset != len(data):
        raise ProtocolError("buffer lengths do not match the frame size")
    return env, out
```

`src/framelab/protocol/messages.py`:

```python
"""Constructors for the envelopes the Python side sends."""

from __future__ import annotations

from typing import Any

from .schema import PROTOCOL_VERSION, Envelope


def make_response(msg_id: str, result: Any) -> Envelope:
    return {"v": PROTOCOL_VERSION, "id": msg_id, "type": "res", "result": result}


def make_error(msg_id: str, code: str, message: str, traceback: str | None = None) -> Envelope:
    error: dict[str, Any] = {"code": code, "i18n_key": f"errors.{code}", "message": message}
    if traceback is not None:
        error["traceback"] = traceback
    return {"v": PROTOCOL_VERSION, "id": msg_id, "type": "res", "error": error}  # type: ignore[typeddict-item]


def make_event(method: str, params: dict[str, Any], rev: int | None = None) -> Envelope:
    env: Envelope = {"v": PROTOCOL_VERSION, "type": "evt", "method": method, "params": params}
    if rev is not None:
        env["rev"] = rev
    return env
```

`src/framelab/protocol/__init__.py`:

```python
from .codec import ProtocolError, decode_frame, dumps, encode_frame, validate_envelope
from .messages import make_error, make_event, make_response
from .schema import PROTOCOL_VERSION

__all__ = [
    "PROTOCOL_VERSION",
    "ProtocolError",
    "decode_frame",
    "dumps",
    "encode_frame",
    "make_error",
    "make_event",
    "make_response",
    "validate_envelope",
]
```

`src/framelab/protocol/tsgen.py`:

```python
"""Generate TypeScript declarations from a module of TypedDicts, Literal aliases and constants."""

from __future__ import annotations

import collections.abc
import json
import types
import typing
from typing import Any, Literal, NotRequired, Required, Union, get_args, get_origin

HEADER = (
    "// Generated by tools/gen_ts_types.py from framelab.protocol.schema — do not edit.\n"
)


def _literal(value: Any) -> str:
    return json.dumps(value)


def _ts(tp: Any, aliases: dict[Any, str], top: bool = False) -> str:
    if not top:
        try:
            if tp in aliases:
                return aliases[tp]
        except TypeError:
            pass
    if tp is Any:
        return "unknown"
    if tp is str:
        return "string"
    if tp in (int, float):
        return "number"
    if tp is bool:
        return "boolean"
    if tp is None or tp is type(None):
        return "null"
    origin = get_origin(tp)
    if origin in (NotRequired, Required):
        return _ts(get_args(tp)[0], aliases)
    if origin is Literal:
        return " | ".join(_literal(v) for v in get_args(tp))
    if origin in (Union, types.UnionType):
        return " | ".join(_ts(a, aliases) for a in get_args(tp))
    if origin in (list, collections.abc.Sequence):
        inner = _ts(get_args(tp)[0], aliases)
        return f"{inner}[]" if inner.isidentifier() else f"Array<{inner}>"
    if origin is dict:
        return f"Record<string, {_ts(get_args(tp)[1], aliases)}>"
    if typing.is_typeddict(tp):
        return tp.__name__
    raise TypeError(f"cannot translate {tp!r} to TypeScript")


def render_module(module: types.ModuleType) -> str:
    consts: list[tuple[str, Any]] = []
    aliases: dict[Any, str] = {}
    dicts: list[type] = []
    for name, obj in vars(module).items():
        if name.startswith("_"):
            continue
        if typing.is_typeddict(obj) and obj.__module__ == module.__name__:
            dicts.append(obj)
        elif get_origin(obj) is Literal:
            aliases[obj] = name
        elif name.isupper() and isinstance(obj, (int, str)) and not isinstance(obj, bool):
            consts.append((name, obj))
    lines = [HEADER]
    for name, value in consts:
        lines.append(f"export const {name} = {json.dumps(value)} as const;")
    for alias, name in aliases.items():
        lines.append(f"export type {name} = {_ts(alias, aliases, top=True)};")
    for td in dicts:
        hints = typing.get_type_hints(td, include_extras=True)
        lines.append("")
        lines.append(f"export interface {td.__name__} {{")
        for key, tp in hints.items():
            optional = "?" if key in td.__optional_keys__ else ""
            lines.append(f"  {key}{optional}: {_ts(tp, aliases)};")
        lines.append("}")
    return "\n".join(lines) + "\n"
```

`tools/gen_ts_types.py`:

```python
"""Regenerate frontend/src/generated/protocol.ts from framelab.protocol.schema."""

from pathlib import Path

from framelab.protocol import schema
from framelab.protocol.tsgen import render_module

TARGET = Path(__file__).resolve().parents[1] / "frontend/src/generated/protocol.ts"

if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render_module(schema), encoding="utf-8")
    print(f"wrote {TARGET}")
```

- [ ] **Step 4: Generate TS and run tests**

Run: `.venv/bin/python tools/gen_ts_types.py && .venv/bin/python -m pytest tests/test_protocol.py tests/test_tsgen.py -v`
Expected: all PASS; `frontend/src/generated/protocol.ts` exists and starts with the generated header.

- [ ] **Step 5: Commit** ("Add wire protocol: envelopes, binary frames and generated TypeScript types").

---

### Task 7: Session (M0) and Dispatcher

**Files:**
- Create: `src/framelab/session/__init__.py`, `src/framelab/transport/__init__.py`, `src/framelab/transport/dispatcher.py`, `tests/test_session.py`, `tests/test_dispatcher.py`

**Interfaces:**
- Consumes: `RootSpec` (Task 5), `OptionsRegistry` (Task 3), protocol (Task 6).
- Produces: `Session(roots: list[RootSpec], options: OptionsRegistry | None = None)` with `id`, `rev`, `names`, `__getitem__`, `__contains__`, `__len__`, `snapshot() -> SessionSnapshot`, `source_expr(name)`; `Dispatcher(session)` with `register(method, handler)`, `handle(env, buffers) -> tuple[Envelope, list[bytes]] | None`, `add_client(send) -> remove`, `emit(method, params=None, buffers=())`, `client_count`; `Reply(result, buffers=[])`; `ProtocolMismatch`. Handler signature: `handler(params: dict, buffers: list[bytes]) -> Any | Reply`. Built-in methods: `session.hello`, `session.snapshot`, `app.ping`.

- [ ] **Step 1: Write failing tests**

`tests/test_session.py`:

```python
import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.options import build_default_registry
from framelab.session import Session


def make(**frames):
    return Session([RootSpec(k, v, None) for k, v in frames.items()], build_default_registry())


def test_snapshot_lists_roots_with_shape():
    ventas = pd.DataFrame({"a": range(1000), "b": 0, "c": 0, "d": 0, "e": 0})
    s = make(ventas=ventas, precios=ventas["a"])
    snap = s.snapshot()
    assert snap["rev"] == 0
    assert snap["session_id"] == s.id
    assert snap["roots"] == [
        {"id": "n1", "name": "ventas", "kind": "DataFrame", "shape": [1000, 5]},
        {"id": "n2", "name": "precios", "kind": "Series", "shape": [1000]},
    ]
    assert any(o["key"] == "general.theme" for o in snap["options"])


def test_roots_are_frozen_against_later_mutation():
    ventas = pd.DataFrame({"a": [1, 2, 3]})
    s = make(ventas=ventas)
    ventas.loc[0, "a"] = 99
    assert s["ventas"].loc[0, "a"] == 1


def test_rejects_non_pandas():
    with pytest.raises(TypeError, match="DataFrame or Series"):
        make(x=[1, 2, 3])


def test_mapping_protocol_and_repr():
    s = make(ventas=pd.DataFrame({"a": [1]}))
    assert "ventas" in s and len(s) == 1 and s.names == ["ventas"]
    assert "ventas" in repr(s)
```

`tests/test_dispatcher.py`:

```python
import pandas as pd

from framelab import __version__
from framelab.naming import RootSpec
from framelab.protocol import PROTOCOL_VERSION
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher, Reply


def dispatcher():
    return Dispatcher(Session([RootSpec("ventas", pd.DataFrame({"a": [1]}), None)]))


def req(method, params=None, msg_id="c1"):
    env = {"v": PROTOCOL_VERSION, "id": msg_id, "type": "req", "method": method}
    if params is not None:
        env["params"] = params
    return env


def test_hello_ok():
    d = dispatcher()
    env, bufs = d.handle(req("session.hello", {"protocol_version": PROTOCOL_VERSION, "client": "ws"}), [])
    assert env["result"] == {
        "protocol_version": PROTOCOL_VERSION,
        "framelab_version": __version__,
        "session_id": d.session.id,
    }
    assert bufs == []


def test_hello_mismatch():
    env, _ = dispatcher().handle(req("session.hello", {"protocol_version": 999, "client": "ws"}), [])
    assert env["error"]["code"] == "protocol_mismatch"


def test_snapshot():
    env, _ = dispatcher().handle(req("session.snapshot"), [])
    assert env["result"]["roots"][0]["name"] == "ventas"


def test_unknown_method():
    env, _ = dispatcher().handle(req("nope.nope"), [])
    assert env["error"]["code"] == "unknown_method"
    assert env["id"] == "c1"


def test_handler_exception_becomes_internal_error_with_traceback():
    d = dispatcher()
    d.register("boom", lambda params, bufs: 1 / 0)
    env, _ = d.handle(req("boom"), [])
    assert env["error"]["code"] == "internal"
    assert "ZeroDivisionError" in env["error"]["message"]
    assert "Traceback" in env["error"]["traceback"]


def test_reply_with_buffers():
    d = dispatcher()
    d.register("echo", lambda params, bufs: Reply({"n": len(bufs)}, [b"x" + b for b in bufs]))
    env, bufs = d.handle(req("echo"), [b"1", b"2"])
    assert env["result"] == {"n": 2}
    assert bufs == [b"x1", b"x2"]


def test_cancel_is_ignored_and_non_requests_rejected():
    d = dispatcher()
    assert d.handle({"v": PROTOCOL_VERSION, "id": "c1", "type": "cancel"}, []) is None
    env, _ = d.handle({"v": PROTOCOL_VERSION, "id": "c1", "type": "res"}, [])
    assert env["error"]["code"] == "bad_request"


def test_emit_reaches_clients_until_removed():
    d = dispatcher()
    got = []
    remove = d.add_client(lambda env, bufs: got.append((env["method"], bufs)))
    assert d.client_count == 1
    d.emit("x.changed", {"a": 1}, [b"z"])
    remove()
    d.emit("x.changed", {"a": 2})
    assert got == [("x.changed", [b"z"])]
    assert d.client_count == 0


def test_emit_survives_a_failing_client():
    d = dispatcher()
    got = []
    d.add_client(lambda env, bufs: (_ for _ in ()).throw(RuntimeError("dead")))
    d.add_client(lambda env, bufs: got.append(env["method"]))
    d.emit("ping")
    assert got == ["ping"]
```

- [ ] **Step 2: Run** → FAIL (modules missing).

- [ ] **Step 3: Implement**

`src/framelab/session/__init__.py`:

```python
"""Session: the Python-side source of truth (M0: frozen roots + snapshot)."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..naming import RootSpec
from ..options import OptionsRegistry
from ..options import registry as default_registry
from ..protocol.schema import SessionSnapshot

__all__ = ["Session"]


@dataclass(frozen=True)
class _Root:
    id: str
    name: str
    obj: pd.DataFrame | pd.Series
    source_expr: str | None


class Session:
    def __init__(self, roots: list[RootSpec], options: OptionsRegistry | None = None) -> None:
        self.id = secrets.token_hex(8)
        self.rev = 0
        self._options = options if options is not None else default_registry
        self._roots: dict[str, _Root] = {}
        for i, spec in enumerate(roots, start=1):
            if not isinstance(spec.obj, (pd.DataFrame, pd.Series)):
                raise TypeError(
                    "framelab.explore expects pandas DataFrame or Series objects; "
                    f"got {type(spec.obj).__name__} for {spec.name!r}"
                )
            frozen = spec.obj.copy(deep=False)
            self._roots[spec.name] = _Root(f"n{i}", spec.name, frozen, spec.source_expr)
        self.widget: Any = None

    @property
    def names(self) -> list[str]:
        return list(self._roots)

    def __getitem__(self, name: str) -> pd.DataFrame | pd.Series:
        return self._roots[name].obj

    def __contains__(self, name: object) -> bool:
        return name in self._roots

    def __len__(self) -> int:
        return len(self._roots)

    def __iter__(self) -> Iterator[str]:
        return iter(self._roots)

    def source_expr(self, name: str) -> str | None:
        return self._roots[name].source_expr

    def snapshot(self) -> SessionSnapshot:
        return {
            "rev": self.rev,
            "session_id": self.id,
            "roots": [
                {
                    "id": r.id,
                    "name": r.name,
                    "kind": "DataFrame" if isinstance(r.obj, pd.DataFrame) else "Series",
                    "shape": [int(n) for n in r.obj.shape],
                }
                for r in self._roots.values()
            ],
            "options": self._options.describe(),  # type: ignore[typeddict-item]
        }

    def __repr__(self) -> str:
        return f"<framelab.Session {self.id}: {', '.join(self.names)}>"
```

`src/framelab/transport/__init__.py`: empty docstring module `"""Transports between the Python session and the frontend."""`.

`src/framelab/transport/dispatcher.py`:

```python
"""Transport-agnostic request handling and event fan-out."""

from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .. import __version__
from ..protocol import PROTOCOL_VERSION, make_error, make_event, make_response
from ..protocol.schema import Envelope
from ..session import Session

__all__ = ["Dispatcher", "ProtocolMismatch", "Reply"]

log = logging.getLogger("framelab")

Handler = Callable[[dict[str, Any], list[bytes]], Any]
Send = Callable[[Envelope, list[bytes]], None]


class ProtocolMismatch(Exception):
    """Client and server speak different protocol versions."""


@dataclass
class Reply:
    result: Any
    buffers: list[bytes] = field(default_factory=list)


class Dispatcher:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._handlers: dict[str, Handler] = {}
        self._clients: dict[int, Send] = {}
        self._next_client = 0
        self._lock = threading.Lock()
        self.register("session.hello", self._hello)
        self.register("session.snapshot", lambda params, buffers: self.session.snapshot())
        self.register("app.ping", lambda params, buffers: {"pong": True})

    def register(self, method: str, handler: Handler) -> None:
        if method in self._handlers:
            raise ValueError(f"handler for {method!r} already registered")
        self._handlers[method] = handler

    def handle(self, env: Envelope, buffers: list[bytes]) -> tuple[Envelope, list[bytes]] | None:
        kind = env["type"]
        msg_id = env.get("id", "")
        if kind == "cancel":
            return None
        if kind != "req":
            return make_error(msg_id, "bad_request", f"unexpected message type {kind!r}"), []
        method = env.get("method", "")
        handler = self._handlers.get(method)
        if handler is None:
            return make_error(msg_id, "unknown_method", f"unknown method {method!r}"), []
        try:
            out = handler(env.get("params", {}), buffers)
        except ProtocolMismatch as exc:
            return make_error(msg_id, "protocol_mismatch", str(exc)), []
        except Exception as exc:
            return (
                make_error(msg_id, "internal", f"{type(exc).__name__}: {exc}", traceback.format_exc()),
                [],
            )
        if isinstance(out, Reply):
            return make_response(msg_id, out.result), list(out.buffers)
        return make_response(msg_id, out), []

    def add_client(self, send: Send) -> Callable[[], None]:
        with self._lock:
            key = self._next_client
            self._next_client += 1
            self._clients[key] = send

        def remove() -> None:
            with self._lock:
                self._clients.pop(key, None)

        return remove

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def emit(self, method: str, params: dict[str, Any] | None = None, buffers: Iterable[bytes] = ()) -> None:
        env = make_event(method, params or {}, rev=self.session.rev)
        payload = list(buffers)
        with self._lock:
            clients = list(self._clients.values())
        for send in clients:
            try:
                send(env, payload)
            except Exception:
                log.exception("framelab: failed to deliver %s to a client", method)

    def _hello(self, params: dict[str, Any], buffers: list[bytes]) -> dict[str, Any]:
        version = params.get("protocol_version")
        if version != PROTOCOL_VERSION:
            raise ProtocolMismatch(
                f"the UI speaks protocol {version!r} but Python speaks {PROTOCOL_VERSION}"
            )
        return {
            "protocol_version": PROTOCOL_VERSION,
            "framelab_version": __version__,
            "session_id": self.session.id,
        }
```

Circular import note: `framelab/__init__.py` defines `__version__` before importing modules that import it. Move `__version__` above the imports in `__init__.py`:

```python
"""framelab — explore, transform and plot pandas DataFrames without writing code."""

__version__ = "0.0.1.dev0"

from .options import get_option, options, reset_option, set_option  # noqa: E402

__all__ = ["__version__", "get_option", "options", "reset_option", "set_option"]
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_session.py tests/test_dispatcher.py -v` → PASS.
- [ ] **Step 5: Commit** ("Add Session snapshot and transport-agnostic Dispatcher").

---

### Task 8: Secure local server (Starlette + uvicorn thread)

**Files:**
- Create: `src/framelab/_paths.py`, `src/framelab/transport/server.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `Dispatcher` (Task 7), codec (Task 6).
- Produces: `FramelabServer(dispatcher, static_dir, *, host="127.0.0.1", port=0, token=None, title="framelab", extra_origins=(), extra_hosts=())` with `start(timeout=10)`, `stop(timeout=5)`, `port`, `url`, `login_url`, `token`, `client_count`, `ever_connected: threading.Event`, `idle_for() -> float`, `write_redirect_file() -> Path`. Cookie name `framelab_token`. `_paths.STATIC_DIR`, `_paths.require_static() -> Path`.
- Security contract (M0 acceptance): only 127.0.0.1; `/` needs `?token=` (sets HttpOnly SameSite=Strict cookie, 303 → `/`) or the cookie; `/static/*` and `/ws` need cookie or `?token=`; `Host` must be `127.0.0.1:PORT`/`localhost:PORT` (+extra_hosts); WS `Origin` must be `http://127.0.0.1:PORT`/`http://localhost:PORT` (+extra_origins); path traversal blocked.

- [ ] **Step 1: Write failing tests `tests/test_server.py`**

```python
import json
import os
import stat
import sys

import httpx
import pandas as pd
import pytest
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

from framelab.naming import RootSpec
from framelab.protocol import PROTOCOL_VERSION, decode_frame, encode_frame
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher, Reply
from framelab.transport.server import COOKIE, FramelabServer


@pytest.fixture
def static_dir(tmp_path):
    (tmp_path / "framelab.js").write_text("export function mountWs() {}", encoding="utf-8")
    (tmp_path / "framelab.css").write_text(".fl-root{}", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("nope", encoding="utf-8")
    return tmp_path


@pytest.fixture
def server(static_dir):
    d = Dispatcher(Session([RootSpec("ventas", pd.DataFrame({"a": range(3)}), None)]))
    d.register("echo", lambda params, bufs: Reply(params, bufs))
    srv = FramelabServer(d, static_dir)
    srv.start()
    yield srv
    srv.stop()


def ws_url(srv):
    return f"ws://127.0.0.1:{srv.port}/ws"


def hello():
    return {"v": PROTOCOL_VERSION, "id": "h", "type": "req", "method": "session.hello",
            "params": {"protocol_version": PROTOCOL_VERSION, "client": "ws"}}


def test_binds_loopback_random_port(server):
    assert server.url == f"http://127.0.0.1:{server.port}/"
    assert server.port > 0


def test_index_requires_token(server):
    assert httpx.get(server.url).status_code == 403
    assert httpx.get(server.url + "?token=wrong").status_code == 403


def test_token_login_sets_cookie_then_serves_index(server):
    with httpx.Client() as c:
        r = c.get(server.login_url)
        assert r.status_code == 303 and r.headers["location"] == "/"
        set_cookie = r.headers["set-cookie"].lower()
        assert "httponly" in set_cookie and "samesite=strict" in set_cookie
        r2 = c.get(server.url)
        assert r2.status_code == 200 and "framelab.js" in r2.text


def test_static_requires_auth_and_blocks_traversal(server):
    assert httpx.get(server.url + "static/framelab.js").status_code == 403
    cookies = {COOKIE: server.token}
    assert httpx.get(server.url + "static/framelab.js", cookies=cookies).status_code == 200
    assert httpx.get(server.url + "static/..%2Fsecret.txt", cookies=cookies).status_code == 404
    assert httpx.get(server.url + "static/missing.js", cookies=cookies).status_code == 404


def test_rejects_foreign_host_header(server):
    r = httpx.get(server.login_url, headers={"Host": "evil.example"})
    assert r.status_code == 403


def test_ws_requires_cookie_and_origin(server):
    origin = f"http://127.0.0.1:{server.port}"
    with pytest.raises(InvalidStatus):
        connect(ws_url(server), origin=origin)
    with pytest.raises(InvalidStatus):
        connect(ws_url(server), origin="http://evil.example",
                additional_headers={"Cookie": f"{COOKIE}={server.token}"})
    with connect(ws_url(server), origin=origin,
                 additional_headers={"Cookie": f"{COOKIE}={server.token}"}) as ws:
        ws.send(encode_frame(hello()))
        env, _ = decode_frame(ws.recv(timeout=5))
        assert env["result"]["protocol_version"] == PROTOCOL_VERSION
    assert server.ever_connected.is_set()


def test_ws_binary_roundtrip_and_events(server):
    origin = f"http://127.0.0.1:{server.port}"
    with connect(ws_url(server) + f"?token={server.token}", origin=origin) as ws:
        ws.send(encode_frame({"v": PROTOCOL_VERSION, "id": "e", "type": "req", "method": "echo",
                              "params": {"x": 1}}, [b"abc"]))
        env, bufs = decode_frame(ws.recv(timeout=5))
        assert env["result"] == {"x": 1} and bufs == [b"abc"]
        server.dispatcher.emit("test.event", {"n": 1})
        env, _ = decode_frame(ws.recv(timeout=5))
        assert env["type"] == "evt" and env["method"] == "test.event"


def test_bad_frame_gets_error_not_disconnect(server):
    origin = f"http://127.0.0.1:{server.port}"
    with connect(ws_url(server) + f"?token={server.token}", origin=origin) as ws:
        ws.send("garbage")
        env, _ = decode_frame(ws.recv(timeout=5))
        assert env["error"]["code"] == "bad_request"
        ws.send(encode_frame(hello()))
        env, _ = decode_frame(ws.recv(timeout=5))
        assert "result" in env


def test_idle_tracking(server):
    origin = f"http://127.0.0.1:{server.port}"
    assert server.client_count == 0
    with connect(ws_url(server) + f"?token={server.token}", origin=origin) as ws:
        ws.send(encode_frame(hello()))
        ws.recv(timeout=5)
        assert server.client_count == 1 and server.idle_for() == 0.0
    import time
    deadline = time.monotonic() + 5
    while server.client_count and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.client_count == 0 and server.idle_for() >= 0.0


def test_redirect_file_is_private_and_points_to_login(server):
    path = server.write_redirect_file()
    try:
        text = path.read_text(encoding="utf-8")
        assert json.dumps(server.login_url) in text
        if sys.platform != "win32":
            assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    finally:
        path.unlink()


def test_stop_releases_port(static_dir):
    d = Dispatcher(Session([RootSpec("v", pd.DataFrame({"a": [1]}), None)]))
    srv = FramelabServer(d, static_dir)
    srv.start()
    port = srv.port
    srv.stop()
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"http://127.0.0.1:{port}/", timeout=1)
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_server.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement**

`src/framelab/_paths.py`:

```python
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "_static"


def require_static() -> Path:
    bundle = STATIC_DIR / "framelab.js"
    if not bundle.is_file():
        raise RuntimeError(
            "framelab's frontend bundle is missing. From a source checkout run "
            "`cd frontend && mise exec -- pnpm install && mise exec -- pnpm build`."
        )
    return STATIC_DIR
```

`src/framelab/transport/server.py`:

```python
"""Local HTTP + WebSocket server for window mode (127.0.0.1 only, token protected)."""

from __future__ import annotations

import asyncio
import html
import json
import os
import secrets
import tempfile
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection, Request
from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from ..protocol import ProtocolError, decode_frame, encode_frame, make_error
from .dispatcher import Dispatcher

__all__ = ["COOKIE", "FramelabServer"]

COOKIE = "framelab_token"

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
html,body,#app{{height:100%;margin:0}}
body{{background:#fafafa}}
@media (prefers-color-scheme:dark){{body{{background:#18181b}}}}
.fl-boot{{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
font:13px system-ui,-apple-system,"Segoe UI",sans-serif;color:#71717a;gap:8px}}
.fl-boot i{{width:14px;height:14px;border:2px solid #d4d4d8;border-top-color:#3b82f6;
border-radius:50%;animation:fl-spin .8s linear infinite}}
@keyframes fl-spin{{to{{transform:rotate(360deg)}}}}
</style>
<link rel="stylesheet" href="/static/framelab.css">
</head>
<body>
<div id="app"><div class="fl-boot"><i></i><span>framelab</span></div></div>
<script type="module">
import {{ mountWs }} from "/static/framelab.js";
const el = document.getElementById("app");
el.replaceChildren();
mountWs(el, (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
</script>
</body>
</html>
"""


class FramelabServer:
    def __init__(
        self,
        dispatcher: Dispatcher,
        static_dir: Path | str,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
        title: str = "framelab",
        extra_origins: Iterable[str] = (),
        extra_hosts: Iterable[str] = (),
    ) -> None:
        self.dispatcher = dispatcher
        self.static_dir = Path(static_dir).resolve()
        self.host = host
        self._port = port
        self.token = token or secrets.token_urlsafe(32)
        self.title = title
        self._extra_origins = frozenset(extra_origins)
        self._extra_hosts = frozenset(extra_hosts)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._clients = 0
        self._clients_lock = threading.Lock()
        self._last_disconnect = time.monotonic()
        self.ever_connected = threading.Event()
        self.app = Starlette(
            routes=[
                Route("/", self._index),
                Route("/static/{path:path}", self._static),
                WebSocketRoute("/ws", self._ws),
            ]
        )

    # ---- lifecycle -------------------------------------------------------------
    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}/"

    @property
    def login_url(self) -> str:
        return f"{self.url}?token={self.token}"

    def start(self, timeout: float = 10.0) -> None:
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self._port,
            log_level="warning",
            lifespan="off",
            ws="websockets-sansio",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="framelab-server", daemon=True)
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive():
                raise RuntimeError("framelab's local server failed to start")
            if time.monotonic() > deadline:
                raise TimeoutError("framelab's local server did not start in time")
            time.sleep(0.01)
        self._port = self._server.servers[0].sockets[0].getsockname()[1]

    def stop(self, timeout: float = 5.0) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout)

    # ---- client tracking ---------------------------------------------------------
    @property
    def client_count(self) -> int:
        with self._clients_lock:
            return self._clients

    def idle_for(self) -> float:
        with self._clients_lock:
            return 0.0 if self._clients else time.monotonic() - self._last_disconnect

    def _joined(self) -> None:
        with self._clients_lock:
            self._clients += 1
        self.ever_connected.set()

    def _left(self) -> None:
        with self._clients_lock:
            self._clients -= 1
            self._last_disconnect = time.monotonic()

    def write_redirect_file(self) -> Path:
        fd, name = tempfile.mkstemp(prefix="framelab-", suffix=".html")
        target = json.dumps(self.login_url)
        content = (
            '<!doctype html><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0;url={html.escape(self.login_url)}">'
            f"<script>location.replace({target})</script>"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(name, 0o600)
        return Path(name)

    # ---- security ------------------------------------------------------------------
    def _host_ok(self, conn: HTTPConnection) -> bool:
        allowed = {f"127.0.0.1:{self._port}", f"localhost:{self._port}"} | self._extra_hosts
        return conn.headers.get("host") in allowed

    def _origin_ok(self, conn: HTTPConnection) -> bool:
        allowed = {f"http://127.0.0.1:{self._port}", f"http://localhost:{self._port}"}
        return conn.headers.get("origin") in allowed | self._extra_origins

    def _token_matches(self, value: str | None) -> bool:
        return value is not None and secrets.compare_digest(value, self.token)

    def _authed(self, conn: HTTPConnection) -> bool:
        return self._token_matches(conn.cookies.get(COOKIE)) or self._token_matches(
            conn.query_params.get("token")
        )

    # ---- routes ------------------------------------------------------------------------
    async def _index(self, request: Request) -> Response:
        if not self._host_ok(request):
            return PlainTextResponse("forbidden", status_code=403)
        query_token = request.query_params.get("token")
        if query_token is not None:
            if not self._token_matches(query_token):
                return PlainTextResponse("forbidden", status_code=403)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(COOKIE, self.token, httponly=True, samesite="strict", path="/")
            return response
        if not self._token_matches(request.cookies.get(COOKIE)):
            return PlainTextResponse("forbidden", status_code=403)
        return HTMLResponse(
            INDEX_TEMPLATE.format(title=html.escape(self.title)),
            headers={"Cache-Control": "no-store"},
        )

    async def _static(self, request: Request) -> Response:
        if not (self._host_ok(request) and self._authed(request)):
            return PlainTextResponse("forbidden", status_code=403)
        target = (self.static_dir / request.path_params["path"]).resolve()
        if not target.is_relative_to(self.static_dir) or not target.is_file():
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(target, headers={"Cache-Control": "no-store"})

    async def _ws(self, ws: WebSocket) -> None:
        if not (self._host_ok(ws) and self._origin_ok(ws) and self._authed(ws)):
            await ws.close(code=4403)
            return
        await ws.accept()
        loop = asyncio.get_running_loop()
        send_lock = asyncio.Lock()

        async def send_frame(frame: bytes | str) -> None:
            async with send_lock:
                if isinstance(frame, bytes):
                    await ws.send_bytes(frame)
                else:
                    await ws.send_text(frame)

        def send_from_any_thread(env: Any, buffers: list[bytes]) -> None:
            asyncio.run_coroutine_threadsafe(send_frame(encode_frame(env, buffers)), loop)

        remove = self.dispatcher.add_client(send_from_any_thread)
        self._joined()
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if data is None:
                    data = message.get("text", "")
                try:
                    env, buffers = decode_frame(data)
                except ProtocolError as exc:
                    await send_frame(encode_frame(make_error("", "bad_request", str(exc))))
                    continue
                reply = await run_in_threadpool(self.dispatcher.handle, env, buffers)
                if reply is not None:
                    await send_frame(encode_frame(*reply))
        finally:
            remove()
            self._left()
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_server.py -v` → PASS. If `connect(..., origin=...)` keyword is not accepted by the installed websockets version, pass `additional_headers={"Origin": ...}` instead and re-run.
- [ ] **Step 5: Commit** ("Add token-protected local server with Host/Origin checks").

---

### Task 9: Frontend skeleton (single ESM bundle)

**Files (all under `frontend/`):**
- Create: `package.json`, `pnpm-lock.yaml` (generated), `tsconfig.json`, `vite.config.ts`, `src/index.tsx`, `src/transport/{types.ts,emitter.ts,codec.ts,ws.ts,anywidget.ts,rpc.ts}`, `src/state/{store.ts,context.tsx}`, `src/ui/portal.tsx`, `src/i18n/{index.ts,locales/en.json,locales/es.json}`, `src/theme/tokens.css`, `src/styles/{index.css,reset.css}`, `src/app/{App.tsx,Shell.tsx,Loader.tsx}`
- Already generated: `src/generated/protocol.ts` (Task 6)

**Interfaces:**
- Consumes: generated `Envelope`, `HelloResult`, `SessionSnapshot`, `PROTOCOL_VERSION`.
- Produces: bundle `src/framelab/_static/framelab.js` exporting `mount(el, transport)`, `mountWs(el, wsUrl)`, and `default { render({model, el}) }` (anywidget AFM); `src/framelab/_static/framelab.css`.

- [ ] **Step 1: Initialise the package with exact versions**

```bash
mkdir -p frontend && cd frontend
cat > package.json <<'EOF'
{
  "name": "framelab-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "packageManager": "pnpm@12.6.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "typecheck": "tsc --noEmit",
    "lint": "oxlint src"
  }
}
EOF
mise exec -- pnpm add -E react@19.3.0 react-dom@19.3.0 zustand@5.0.15 i18next@26.4.2 react-i18next@17.0.15
mise exec -- pnpm add -E -D vite@8.3.0 @vitejs/plugin-react@6.1.1 typescript@7.0.2 @types/react @types/react-dom tailwindcss@4.3.3 @tailwindcss/vite@4.3.3 oxlint@1.85.0 @anywidget/types@0.4.0
```

Expected: `node_modules/` created, `pnpm-lock.yaml` written, no peer-dependency errors (warnings about `@types/*` versions are fine).

- [ ] **Step 2: Config files**

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "types": ["vite/client"]
  },
  "include": ["src", "vite.config.ts"]
}
```

`frontend/vite.config.ts`:

```ts
import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const here = import.meta.dirname;

export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],
  define: {
    "process.env.NODE_ENV": JSON.stringify(command === "build" ? "production" : "development"),
  },
  build: {
    outDir: resolve(here, "../src/framelab/_static"),
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
    lib: {
      entry: resolve(here, "src/index.tsx"),
      formats: ["es"],
      fileName: () => "framelab.js",
      cssFileName: "framelab",
    },
    rolldownOptions: { output: { codeSplitting: false } },
  },
  server: {
    port: 5173,
    proxy: { "/ws": { target: "ws://127.0.0.1:8765", ws: true } },
  },
}));
```

- [ ] **Step 3: Transport layer**

`src/transport/types.ts`:

```ts
import type { Envelope } from "../generated/protocol";

export type TransportStatus = "connecting" | "open" | "closed";

export interface Transport {
  readonly kind: "ws" | "anywidget";
  send(env: Envelope, buffers?: ArrayBuffer[]): void;
  onMessage(cb: (env: Envelope, buffers: DataView[]) => void): () => void;
  onStatus(cb: (status: TransportStatus) => void): () => void;
  status(): TransportStatus;
  close(): void;
}
```

`src/transport/emitter.ts`:

```ts
export interface Emitter<T extends unknown[]> {
  on(cb: (...args: T) => void): () => void;
  emit(...args: T): void;
  clear(): void;
}

export function createEmitter<T extends unknown[]>(): Emitter<T> {
  const listeners = new Set<(...args: T) => void>();
  return {
    on(cb) {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },
    emit(...args) {
      for (const cb of [...listeners]) cb(...args);
    },
    clear() {
      listeners.clear();
    },
  };
}
```

`src/transport/codec.ts`:

```ts
import type { Envelope } from "../generated/protocol";

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function encodeFrame(env: Envelope, buffers: ArrayBuffer[] = []): string | ArrayBuffer {
  if (buffers.length === 0) return JSON.stringify(env);
  const header = encoder.encode(JSON.stringify({ ...env, buffers: buffers.map((b) => b.byteLength) }));
  const total = 4 + header.byteLength + buffers.reduce((n, b) => n + b.byteLength, 0);
  const out = new Uint8Array(total);
  new DataView(out.buffer).setUint32(0, header.byteLength, false);
  out.set(header, 4);
  let offset = 4 + header.byteLength;
  for (const b of buffers) {
    out.set(new Uint8Array(b), offset);
    offset += b.byteLength;
  }
  return out.buffer;
}

export function decodeFrame(data: string | ArrayBuffer): { env: Envelope; buffers: DataView[] } {
  if (typeof data === "string") return { env: JSON.parse(data) as Envelope, buffers: [] };
  const view = new DataView(data);
  const n = view.getUint32(0, false);
  const env = JSON.parse(decoder.decode(new Uint8Array(data, 4, n))) as Envelope;
  const buffers: DataView[] = [];
  let offset = 4 + n;
  for (const length of env.buffers ?? []) {
    buffers.push(new DataView(data, offset, length));
    offset += length;
  }
  return { env, buffers };
}
```

`src/transport/ws.ts`:

```ts
import type { Envelope } from "../generated/protocol";
import { decodeFrame, encodeFrame } from "./codec";
import { createEmitter } from "./emitter";
import type { Transport, TransportStatus } from "./types";

export function createWsTransport(url: string, maxDelayMs = 5000): Transport {
  const messages = createEmitter<[Envelope, DataView[]]>();
  const statuses = createEmitter<[TransportStatus]>();
  const queue: (string | ArrayBuffer)[] = [];
  let socket: WebSocket | null = null;
  let current: TransportStatus = "connecting";
  let closedByUser = false;
  let attempt = 0;

  const setStatus = (status: TransportStatus) => {
    current = status;
    statuses.emit(status);
  };

  const connect = () => {
    setStatus("connecting");
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    socket = ws;
    ws.onopen = () => {
      attempt = 0;
      setStatus("open");
      while (queue.length > 0) ws.send(queue.shift()!);
    };
    ws.onmessage = (event) => {
      const { env, buffers } = decodeFrame(event.data as string | ArrayBuffer);
      messages.emit(env, buffers);
    };
    ws.onclose = () => {
      socket = null;
      if (closedByUser) {
        setStatus("closed");
        return;
      }
      setStatus("connecting");
      const delay = Math.min(maxDelayMs, 250 * 2 ** attempt++);
      setTimeout(connect, delay);
    };
  };

  connect();

  return {
    kind: "ws",
    send(env, buffers = []) {
      const frame = encodeFrame(env, buffers);
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(frame);
      else queue.push(frame);
    },
    onMessage: messages.on,
    onStatus: statuses.on,
    status: () => current,
    close() {
      closedByUser = true;
      socket?.close();
      messages.clear();
    },
  };
}
```

`src/transport/anywidget.ts`:

```ts
import type { AnyModel } from "@anywidget/types";
import type { Envelope } from "../generated/protocol";
import { createEmitter } from "./emitter";
import type { Transport, TransportStatus } from "./types";

export function createAnyWidgetTransport(model: AnyModel): Transport {
  const messages = createEmitter<[Envelope, DataView[]]>();
  const statuses = createEmitter<[TransportStatus]>();
  const handler = (msg: unknown, buffers: DataView[]) => messages.emit(msg as Envelope, buffers ?? []);
  model.on("msg:custom", handler);
  return {
    kind: "anywidget",
    send(env, buffers = []) {
      model.send(env, undefined, buffers);
    },
    onMessage: messages.on,
    onStatus: statuses.on,
    status: () => "open",
    close() {
      model.off("msg:custom", handler);
      messages.clear();
      statuses.clear();
    },
  };
}
```

`src/transport/rpc.ts`:

```ts
import { type Envelope, PROTOCOL_VERSION } from "../generated/protocol";
import type { Transport } from "./types";

export class RpcError extends Error {
  constructor(
    readonly code: string,
    readonly i18nKey: string,
    message: string,
    readonly traceback?: string,
  ) {
    super(message);
  }
}

type EventCallback = (params: Record<string, unknown>, buffers: DataView[], env: Envelope) => void;

export interface Rpc {
  request<T = unknown>(
    method: string,
    params?: Record<string, unknown>,
    buffers?: ArrayBuffer[],
  ): Promise<{ result: T; buffers: DataView[] }>;
  onEvent(method: string, cb: EventCallback): () => void;
  dispose(): void;
}

interface Pending {
  resolve: (value: { result: unknown; buffers: DataView[] }) => void;
  reject: (reason: RpcError) => void;
  timer: ReturnType<typeof setTimeout>;
}

export function createRpc(transport: Transport, timeoutMs = 30_000): Rpc {
  let seq = 0;
  const pending = new Map<string, Pending>();
  const events = new Map<string, Set<EventCallback>>();

  const off = transport.onMessage((env, buffers) => {
    if (env.type === "res" && env.id !== undefined) {
      const entry = pending.get(env.id);
      if (!entry) return;
      pending.delete(env.id);
      clearTimeout(entry.timer);
      if (env.error) {
        const e = env.error;
        entry.reject(new RpcError(e.code, e.i18n_key, e.message, e.traceback));
      } else {
        entry.resolve({ result: env.result, buffers });
      }
    } else if (env.type === "evt" && env.method) {
      for (const key of [env.method, "*"]) {
        for (const cb of events.get(key) ?? []) cb(env.params ?? {}, buffers, env);
      }
    }
  });

  return {
    request<T>(method: string, params: Record<string, unknown> = {}, buffers: ArrayBuffer[] = []) {
      const id = `c${++seq}`;
      return new Promise<{ result: T; buffers: DataView[] }>((resolve, reject) => {
        const timer = setTimeout(() => {
          pending.delete(id);
          reject(new RpcError("timeout", "errors.timeout", `${method} timed out`));
        }, timeoutMs);
        pending.set(id, {
          resolve: resolve as Pending["resolve"],
          reject,
          timer,
        });
        transport.send({ v: PROTOCOL_VERSION, id, type: "req", method, params }, buffers);
      });
    },
    onEvent(method, cb) {
      const set = events.get(method) ?? new Set<EventCallback>();
      set.add(cb);
      events.set(method, set);
      return () => {
        set.delete(cb);
      };
    },
    dispose() {
      off();
      for (const entry of pending.values()) {
        clearTimeout(entry.timer);
        entry.reject(new RpcError("closed", "errors.closed", "connection closed"));
      }
      pending.clear();
      events.clear();
    },
  };
}
```

- [ ] **Step 4: State, portal and i18n**

`src/state/store.ts`:

```ts
import { createStore } from "zustand/vanilla";
import type { HelloResult, SessionSnapshot } from "../generated/protocol";

export type ConnectionState = "connecting" | "ready" | "mismatch" | "error";

export interface AppState {
  connection: ConnectionState;
  error: string | null;
  hello: HelloResult | null;
  snapshot: SessionSnapshot | null;
  setConnection(connection: ConnectionState, error?: string | null): void;
  setHello(hello: HelloResult): void;
  setSnapshot(snapshot: SessionSnapshot): void;
}

export type AppStore = ReturnType<typeof createAppStore>;

export function createAppStore() {
  return createStore<AppState>()((set) => ({
    connection: "connecting",
    error: null,
    hello: null,
    snapshot: null,
    setConnection: (connection, error = null) => set({ connection, error }),
    setHello: (hello) => set({ hello }),
    setSnapshot: (snapshot) => set({ snapshot }),
  }));
}
```

`src/state/context.tsx`:

```tsx
import { createContext, useContext } from "react";
import { useStore } from "zustand";
import type { AppState, AppStore } from "./store";

const StoreContext = createContext<AppStore | null>(null);

export const StoreProvider = StoreContext.Provider;

export function useAppStore<T>(selector: (state: AppState) => T): T {
  const store = useContext(StoreContext);
  if (!store) throw new Error("useAppStore must be used inside <StoreProvider>");
  return useStore(store, selector);
}
```

`src/ui/portal.tsx`:

```tsx
import { createContext, useContext } from "react";

const PortalContext = createContext<HTMLElement | null>(null);

export const PortalProvider = PortalContext.Provider;

/** Element inside `.fl-root` where menus, tooltips and drag ghosts must be portalled. */
export function usePortalContainer(): HTMLElement | null {
  return useContext(PortalContext);
}
```

`src/i18n/index.ts`:

```ts
import i18next, { type i18n } from "i18next";
import en from "./locales/en.json";
import es from "./locales/es.json";

export type Lang = "es" | "en";

export function pickLanguage(pref: unknown, navigatorLangs: readonly string[]): Lang {
  if (pref === "es" || pref === "en") return pref;
  for (const tag of navigatorLangs) {
    const base = tag.toLowerCase().split("-")[0];
    if (base === "es" || base === "en") return base;
  }
  return "en";
}

export function createI18n(lang: Lang): i18n {
  const instance = i18next.createInstance();
  void instance.init({
    lng: lang,
    fallbackLng: "en",
    resources: { en: { translation: en }, es: { translation: es } },
    interpolation: { escapeValue: false },
    initAsync: false,
  });
  return instance;
}
```

`src/i18n/locales/en.json`:

```json
{
  "app": {
    "connecting": "Connecting…",
    "protocolMismatch": "This framelab window does not match the installed Python package. Close it and run explore() again.",
    "error": "Something went wrong"
  },
  "workbench": {
    "roots": "Data",
    "shape": "{{rows}} × {{cols}}",
    "rows": "{{count}} rows"
  },
  "errors": {
    "timeout": "The request took too long",
    "closed": "The connection was closed",
    "internal": "Internal error",
    "unknown_method": "Unknown request",
    "bad_request": "Invalid request",
    "protocol_mismatch": "Version mismatch"
  }
}
```

`src/i18n/locales/es.json`:

```json
{
  "app": {
    "connecting": "Conectando…",
    "protocolMismatch": "Esta ventana de framelab no coincide con el paquete de Python instalado. Cerrala y volvé a ejecutar explore().",
    "error": "Algo salió mal"
  },
  "workbench": {
    "roots": "Datos",
    "shape": "{{rows}} × {{cols}}",
    "rows": "{{count}} filas"
  },
  "errors": {
    "timeout": "La solicitud tardó demasiado",
    "closed": "Se cerró la conexión",
    "internal": "Error interno",
    "unknown_method": "Solicitud desconocida",
    "bad_request": "Solicitud inválida",
    "protocol_mismatch": "Versiones incompatibles"
  }
}
```

- [ ] **Step 5: Styles and theme tokens**

`src/theme/tokens.css`:

```css
.fl-root {
  --fl-bg: #fafafa;
  --fl-panel: #ffffff;
  --fl-fg: #18181b;
  --fl-muted: #71717a;
  --fl-border: #e4e4e7;
  --fl-hover: #f4f4f5;
  --fl-accent: #3b82f6;
  --fl-accent-fg: #ffffff;
  --fl-danger: #dc2626;
  --fl-warning: #d97706;
  --fl-font-sans: "Inter Variable", system-ui, -apple-system, "Segoe UI", sans-serif;
  --fl-font-mono: "JetBrains Mono Variable", ui-monospace, "SFMono-Regular", Menlo, monospace;
  --fl-radius: 6px;
  --fl-duration: 150ms;
  color-scheme: light;
}

.fl-root[data-theme="dark"] {
  --fl-bg: #18181b;
  --fl-panel: #1f1f23;
  --fl-fg: #f4f4f5;
  --fl-muted: #a1a1aa;
  --fl-border: #2e2e33;
  --fl-hover: #27272a;
  color-scheme: dark;
}

@media (prefers-color-scheme: dark) {
  .fl-root[data-theme="system"] {
    --fl-bg: #18181b;
    --fl-panel: #1f1f23;
    --fl-fg: #f4f4f5;
    --fl-muted: #a1a1aa;
    --fl-border: #2e2e33;
    --fl-hover: #27272a;
    color-scheme: dark;
  }
}

.fl-root[data-reduce-motion="true"] {
  --fl-duration: 0ms;
}

@media (prefers-reduced-motion: reduce) {
  .fl-root {
    --fl-duration: 0ms;
  }
}
```

`src/styles/reset.css`:

```css
@layer base {
  .fl-root,
  .fl-root *,
  .fl-root *::before,
  .fl-root *::after {
    box-sizing: border-box;
  }
  .fl-root {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
    font-family: var(--fl-font-sans);
    font-size: 13px;
    line-height: 1.45;
    color: var(--fl-fg);
    background: var(--fl-bg);
    -webkit-font-smoothing: antialiased;
  }
  .fl-root :where(h1, h2, h3, h4, p, ul, ol, figure) {
    margin: 0;
  }
  .fl-root :where(ul, ol) {
    padding: 0;
    list-style: none;
  }
  .fl-root :where(button, input, select, textarea) {
    font: inherit;
    color: inherit;
  }
  .fl-root :where(button) {
    padding: 0;
    border: 0;
    background: none;
    cursor: pointer;
  }
  .fl-root :where(code, pre, kbd) {
    font-family: var(--fl-font-mono);
  }
}
```

`src/styles/index.css`:

```css
@layer theme, base, components, utilities;
@import "tailwindcss/theme.css" layer(theme) prefix(fl);
@import "tailwindcss/utilities.css" layer(utilities) prefix(fl);
@import "../theme/tokens.css";
@import "./reset.css";

@keyframes fl-spin {
  to {
    transform: rotate(360deg);
  }
}
```

- [ ] **Step 6: App, shell and entry point**

`src/app/Loader.tsx`:

```tsx
export function Loader({ label }: { label: string }) {
  return (
    <div className="fl:flex fl:h-full fl:items-center fl:justify-center fl:gap-2" style={{ color: "var(--fl-muted)" }}>
      <span
        aria-hidden
        style={{
          width: 14,
          height: 14,
          borderRadius: "50%",
          border: "2px solid var(--fl-border)",
          borderTopColor: "var(--fl-accent)",
          animation: "fl-spin .8s linear infinite",
        }}
      />
      <span role="status">{label}</span>
    </div>
  );
}
```

`src/app/Shell.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { useAppStore } from "../state/context";
import { Loader } from "./Loader";

export function Shell() {
  const { t } = useTranslation();
  const connection = useAppStore((s) => s.connection);
  const error = useAppStore((s) => s.error);
  const snapshot = useAppStore((s) => s.snapshot);

  if (connection === "connecting") return <Loader label={t("app.connecting")} />;
  if (connection !== "ready" || !snapshot) {
    return (
      <div className="fl:flex fl:h-full fl:flex-col fl:items-center fl:justify-center fl:gap-2 fl:p-6">
        <p style={{ color: "var(--fl-danger)" }}>
          {connection === "mismatch" ? t("app.protocolMismatch") : t("app.error")}
        </p>
        {error ? <pre className="fl:text-xs" style={{ color: "var(--fl-muted)" }}>{error}</pre> : null}
      </div>
    );
  }
  return (
    <main className="fl:flex fl:h-full fl:flex-col fl:gap-2 fl:p-4">
      <h2 className="fl:text-xs fl:uppercase fl:tracking-wide" style={{ color: "var(--fl-muted)" }}>
        {t("workbench.roots")}
      </h2>
      <ul className="fl:flex fl:flex-col fl:gap-1">
        {snapshot.roots.map((root) => (
          <li key={root.id} data-testid="root-item" className="fl:font-mono">
            {root.name} ·{" "}
            {root.shape.length === 2
              ? t("workbench.shape", { rows: root.shape[0], cols: root.shape[1] })
              : t("workbench.rows", { count: root.shape[0] })}
          </li>
        ))}
      </ul>
    </main>
  );
}
```

`src/app/App.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { I18nextProvider } from "react-i18next";
import { useStore } from "zustand";
import { type HelloResult, PROTOCOL_VERSION, type SessionSnapshot } from "../generated/protocol";
import { createI18n, pickLanguage } from "../i18n";
import { StoreProvider } from "../state/context";
import { createAppStore } from "../state/store";
import { createRpc, RpcError } from "../transport/rpc";
import type { Transport } from "../transport/types";
import { PortalProvider } from "../ui/portal";
import { Shell } from "./Shell";

function optionValue(snapshot: SessionSnapshot | null, key: string): unknown {
  return snapshot?.options.find((o) => o.key === key)?.value;
}

function browserLanguages(): readonly string[] {
  return navigator.languages?.length ? navigator.languages : [navigator.language];
}

export function App({ transport }: { transport: Transport }) {
  const [store] = useState(createAppStore);
  const [rpc] = useState(() => createRpc(transport));
  const [portalEl, setPortalEl] = useState<HTMLDivElement | null>(null);
  const snapshot = useStore(store, (s) => s.snapshot);
  const lang = pickLanguage(optionValue(snapshot, "general.language"), browserLanguages());
  const i18n = useMemo(() => createI18n(lang), []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void i18n.changeLanguage(lang);
  }, [i18n, lang]);

  useEffect(() => {
    const state = store.getState();
    const handshake = async () => {
      state.setConnection("connecting");
      try {
        const hello = await rpc.request<HelloResult>("session.hello", {
          protocol_version: PROTOCOL_VERSION,
          client: transport.kind,
        });
        state.setHello(hello.result);
        const snap = await rpc.request<SessionSnapshot>("session.snapshot");
        state.setSnapshot(snap.result);
        state.setConnection("ready");
      } catch (err) {
        if (err instanceof RpcError && err.code === "protocol_mismatch") {
          state.setConnection("mismatch", err.message);
        } else {
          state.setConnection("error", err instanceof Error ? err.message : String(err));
        }
      }
    };
    const offStatus = transport.onStatus((status) => {
      if (status === "open") void handshake();
      else if (status === "connecting") state.setConnection("connecting");
    });
    if (transport.status() === "open") void handshake();
    return () => {
      offStatus();
      rpc.dispose();
    };
  }, [rpc, store, transport]);

  const theme = (optionValue(snapshot, "general.theme") as string | undefined) ?? "system";
  const reduceMotion = optionValue(snapshot, "general.reduce_motion") === true;

  return (
    <StoreProvider value={store}>
      <I18nextProvider i18n={i18n}>
        <PortalProvider value={portalEl}>
          <div
            className="fl-root"
            data-theme={theme}
            data-reduce-motion={reduceMotion ? "true" : "false"}
            data-lm-suppress-shortcuts="true"
            data-jp-suppress-context-menu="true"
          >
            <Shell />
            <div ref={setPortalEl} className="fl-portal" />
          </div>
        </PortalProvider>
      </I18nextProvider>
    </StoreProvider>
  );
}
```

`src/index.tsx`:

```tsx
import "./styles/index.css";
import type { AnyModel } from "@anywidget/types";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { createAnyWidgetTransport } from "./transport/anywidget";
import type { Transport } from "./transport/types";
import { createWsTransport } from "./transport/ws";

export function mount(el: HTMLElement, transport: Transport): () => void {
  const root = createRoot(el);
  root.render(<App transport={transport} />);
  return () => {
    root.unmount();
    transport.close();
  };
}

export function mountWs(el: HTMLElement, wsUrl: string): () => void {
  return mount(el, createWsTransport(wsUrl));
}

export default {
  render({ model, el }: { model: AnyModel<{ height: number }>; el: HTMLElement }) {
    el.style.height = `${model.get("height") ?? 720}px`;
    el.style.position = "relative";
    return mount(el, createAnyWidgetTransport(model));
  },
};
```

- [ ] **Step 7: Typecheck and build**

Run: `cd frontend && mise exec -- pnpm typecheck && mise exec -- pnpm build && ls -la ../src/framelab/_static`
Expected: typecheck passes with 0 errors; `_static/framelab.js` and `_static/framelab.css` exist; no other chunk files. Fix type errors in place (e.g. if `@anywidget/types` model generics differ, use `AnyModel` without the type argument and cast `model.get("height") as number`).

- [ ] **Step 8: Commit** (`frontend/` + generated types; `_static/` is gitignored) ("Add frontend skeleton: transports, RPC, store, i18n, scoped theme").

---

### Task 10: Build hook and packaging (includes spike S9)

**Files:**
- Create: `hatch_build.py`, `tests/test_packaging.py`
- Modify: `pyproject.toml` (add `[tool.hatch.build.hooks.custom]`)

**Interfaces:**
- Produces: `python -m build` → `dist/framelab-0.0.1.dev0-py3-none-any.whl` containing `framelab/_static/framelab.js|css`; sdist containing `_static` + frontend sources (no `node_modules`) that installs without Node.

- [ ] **Step 1: Write failing test `tests/test_packaging.py`**

```python
import os
import subprocess
import sys
import tarfile
import venv
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(out), str(ROOT)], check=True)
    return out


def test_wheel_is_pure_and_contains_bundle(dist):
    (wheel,) = dist.glob("*.whl")
    assert wheel.name.endswith("-py3-none-any.whl")
    names = zipfile.ZipFile(wheel).namelist()
    assert "framelab/_static/framelab.js" in names
    assert "framelab/_static/framelab.css" in names
    assert not any("node_modules" in n for n in names)


def test_sdist_has_sources_and_bundle_but_no_node_modules(dist):
    (sdist,) = dist.glob("*.tar.gz")
    names = tarfile.open(sdist).getnames()
    assert any(n.endswith("src/framelab/_static/framelab.js") for n in names)
    assert any(n.endswith("frontend/package.json") for n in names)
    assert not any("node_modules" in n for n in names)


def test_sdist_installs_without_node(dist, tmp_path):
    (sdist,) = dist.glob("*.tar.gz")
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True)
    py = env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    clean_path = os.pathsep.join(
        p for p in os.environ["PATH"].split(os.pathsep)
        if "mise" not in p and not (Path(p) / "node").exists() and not (Path(p) / "pnpm").exists()
    )
    env = {**os.environ, "PATH": clean_path}
    subprocess.run([str(py), "-m", "pip", "install", "-q", "--no-deps", str(sdist)], check=True, env=env)
    out = subprocess.run(
        [str(py), "-c", "import framelab, pathlib; p = pathlib.Path(framelab.__file__).parent / '_static' / 'framelab.js'; print(p.is_file())"],
        check=True, env=env, capture_output=True, text=True,
    )
    assert out.stdout.strip() == "True"
```

Note: `import framelab` in the fresh venv needs deps only at import of submodules; `framelab/__init__.py` imports `options` only (stdlib), so `--no-deps` works.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_packaging.py -v -m slow` → FAIL on the sdist tests if `_static` is not included / hook missing (wheel test may already pass because `_static` exists from Task 9 — delete `src/framelab/_static` first to prove the hook rebuilds it: `rm -rf src/framelab/_static`).

- [ ] **Step 3: Implement `hatch_build.py` and register it**

```python
"""Hatch build hook: build the frontend bundle when it is missing."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FrontendBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if os.environ.get("FRAMELAB_SKIP_JS") == "1":
            return
        root = Path(self.root)
        bundle = root / "src" / "framelab" / "_static" / "framelab.js"
        if bundle.is_file() and os.environ.get("FRAMELAB_FORCE_JS") != "1":
            return
        frontend = root / "frontend"
        if not (frontend / "package.json").is_file():
            raise RuntimeError(
                "framelab: the frontend bundle is missing and frontend/ sources are not available"
            )
        pnpm = self._pnpm()
        subprocess.run([*pnpm, "install", "--frozen-lockfile"], cwd=frontend, check=True)
        subprocess.run([*pnpm, "run", "build"], cwd=frontend, check=True)
        if not bundle.is_file():
            raise RuntimeError("framelab: the frontend build finished but framelab.js was not produced")

    @staticmethod
    def _pnpm() -> list[str]:
        if shutil.which("mise"):
            return ["mise", "exec", "--", "pnpm"]
        if shutil.which("pnpm"):
            return ["pnpm"]
        raise RuntimeError(
            "framelab: pnpm is required to build the frontend (run `mise install`), "
            "or set FRAMELAB_SKIP_JS=1 to skip it"
        )
```

Append to `pyproject.toml`:

```toml
[tool.hatch.build.hooks.custom]
path = "hatch_build.py"
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_packaging.py -v -m slow` → PASS (3 tests). Then `.venv/bin/pip install -e . -q` still works.
- [ ] **Step 5: Commit** ("Build the frontend in a hatch hook; ship it inside a pure wheel").

---

### Task 11: Inline widget for notebooks (includes spike S2 checks)

**Files:**
- Create: `src/framelab/transport/widget.py`, `tests/test_widget.py`

**Interfaces:**
- Consumes: `Dispatcher`, `require_static()`.
- Produces: `FramelabWidget(dispatcher, height=720)` (anywidget) — Python → JS via `self.send(env, buffers)`, JS → Python via `on_msg`.

- [ ] **Step 1: Write failing tests `tests/test_widget.py`**

```python
import pandas as pd
import pytest

from framelab.naming import RootSpec
from framelab.protocol import PROTOCOL_VERSION
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher

widget_mod = pytest.importorskip("framelab.transport.widget")


def make_widget(monkeypatch):
    sent = []
    d = Dispatcher(Session([RootSpec("ventas", pd.DataFrame({"a": [1, 2]}), None)]))
    w = widget_mod.FramelabWidget(d)
    monkeypatch.setattr(w, "send", lambda content, buffers=None: sent.append((content, buffers)))
    return w, d, sent


def test_widget_answers_requests(monkeypatch):
    w, d, sent = make_widget(monkeypatch)
    w._on_msg(w, {"v": PROTOCOL_VERSION, "id": "c1", "type": "req", "method": "session.snapshot"}, [])
    (content, buffers) = sent[-1]
    assert content["id"] == "c1" and content["result"]["roots"][0]["name"] == "ventas"
    assert buffers is None


def test_widget_receives_events(monkeypatch):
    w, d, sent = make_widget(monkeypatch)
    d.emit("test.event", {"x": 1}, [b"abc"])
    content, buffers = sent[-1]
    assert content["method"] == "test.event" and buffers == [b"abc"]


def test_bad_message_returns_error(monkeypatch):
    w, d, sent = make_widget(monkeypatch)
    w._on_msg(w, {"v": 999}, [])
    assert sent[-1][0]["error"]["code"] == "bad_request"


def test_height_trait(monkeypatch):
    w, _, _ = make_widget(monkeypatch)
    assert w.height == 720
```

`tests/test_notebook.py` (slow, validates the widget renders as a widget output in a real kernel):

```python
import nbformat
import pytest
from nbclient import NotebookClient

pytestmark = pytest.mark.slow


def test_explore_displays_widget_in_kernel():
    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell(
        "import pandas as pd, framelab as fl\n"
        "ventas = pd.DataFrame({'a': range(1000), 'b': 0, 'c': 0, 'd': 0, 'e': 0})\n"
        "s = fl.explore(ventas)\n"
        "print(s.names)"
    ))
    NotebookClient(nb, timeout=120, kernel_name="python3").execute()
    outputs = nb.cells[0].outputs
    assert any("application/vnd.jupyter.widget-view+json" in o.get("data", {}) for o in outputs)
    assert any("['ventas']" in o.get("text", "") for o in outputs)
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_widget.py -v` → FAIL (module missing). (`test_notebook.py` fails until Task 12 adds `explore`.)

- [ ] **Step 3: Implement `src/framelab/transport/widget.py`**

```python
"""anywidget adapter: the same frontend bundle rendered inside notebook outputs."""

from __future__ import annotations

from typing import Any

import anywidget
import traitlets

from .._paths import require_static
from ..protocol import ProtocolError, make_error, validate_envelope
from .dispatcher import Dispatcher

_STATIC = require_static()


class FramelabWidget(anywidget.AnyWidget):
    _esm = _STATIC / "framelab.js"
    _css = _STATIC / "framelab.css"
    height = traitlets.Int(720).tag(sync=True)

    def __init__(self, dispatcher: Dispatcher, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._dispatcher = dispatcher
        self.on_msg(self._on_msg)
        self._remove_client = dispatcher.add_client(self._send_envelope)

    def _send_envelope(self, env: Any, buffers: list[bytes]) -> None:
        self.send(env, buffers=list(buffers) or None)

    def _on_msg(self, _widget: Any, content: Any, buffers: list[Any]) -> None:
        try:
            env = validate_envelope(content)
        except ProtocolError as exc:
            self._send_envelope(make_error("", "bad_request", str(exc)), [])
            return
        reply = self._dispatcher.handle(env, [bytes(b) for b in buffers])
        if reply is not None:
            self._send_envelope(*reply)

    def close(self) -> None:
        self._remove_client()
        super().close()
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_widget.py -v` → PASS.
- [ ] **Step 5: Commit** ("Add anywidget adapter for notebook mode").

---

### Task 12: Window launcher chain and `fl.explore()` (includes spike S4, E2E #1)

**Files:**
- Create: `src/framelab/launch/{__init__.py,browsers.py,chromium.py,webview.py,browser.py}`, `src/framelab/api.py`, `tests/test_launch.py`, `tests/test_api.py`, `tests/test_window_e2e.py`
- Modify: `src/framelab/__init__.py`

**Interfaces:**
- Consumes: `FramelabServer` (Task 8), `FramelabWidget` (Task 11), `detect_env/resolve_mode` (Task 4), `resolve_root_names` (Task 5), `Session`, `Dispatcher`.
- Produces: `find_chromium(*, platform=None, which=shutil.which, exists=os.path.exists) -> str | None`; `build_command(browser, target, *, profile_dir, width=1400, height=900, extra_args=()) -> list[str]`; `launch_app_window(browser, target, *, width=1400, height=900, extra_args=None) -> ChromiumWindow` (`wait(timeout=None) -> int`, `close()`); `pywebview_available()`, `run_pywebview(url, title, width, height)`; `open_in_browser(server, *, first_connect_timeout=120.0, grace=60.0, poll=0.25, opener=webbrowser.open, sleep=time.sleep)`; `default_order(platform=None)`, `open_window(server, *, title="framelab", order=None) -> str`; `explore(*dfs, name=None, mode=None, **named) -> Session`; `last_session() -> Session | None`.

- [ ] **Step 1: Write failing tests**

`tests/test_launch.py`:

```python
import os
import sys
import threading
from pathlib import Path

import pytest

from framelab.launch import default_order, open_window
from framelab.launch.browser import open_in_browser
from framelab.launch.browsers import find_chromium
from framelab.launch.chromium import build_command


def test_find_chromium_linux_prefers_first_available():
    found = find_chromium(platform="linux", which=lambda n: f"/usr/bin/{n}" if n == "google-chrome" else None)
    assert found == "/usr/bin/google-chrome"


def test_find_chromium_none_when_missing():
    assert find_chromium(platform="linux", which=lambda n: None) is None


def test_find_chromium_env_override(monkeypatch, tmp_path):
    exe = tmp_path / "mybrowser"
    exe.write_text("")
    monkeypatch.setenv("FRAMELAB_BROWSER", str(exe))
    assert find_chromium(platform="linux", which=lambda n: None) == str(exe)


def test_find_chromium_macos():
    path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    assert find_chromium(platform="darwin", which=lambda n: None, exists=lambda p: p == path) == path


def test_command_never_contains_token(tmp_path):
    target = (tmp_path / "redirect.html").as_uri()
    cmd = build_command("/usr/bin/chromium", target, profile_dir=tmp_path / "p")
    assert cmd[0] == "/usr/bin/chromium"
    assert f"--app={target}" in cmd
    assert f"--user-data-dir={tmp_path / 'p'}" in cmd
    assert "--no-first-run" in cmd and "--no-default-browser-check" in cmd
    assert not any("token" in part for part in cmd)


def test_default_order_per_platform():
    assert default_order("linux")[0] == "chromium"
    assert default_order("win32")[0] == "pywebview"
    assert default_order("darwin")[0] == "pywebview"


class FakeServer:
    def __init__(self):
        self.ever_connected = threading.Event()
        self._idle = 0.0
        self.login_url = "http://127.0.0.1:1/?token=t"

    def write_redirect_file(self):
        return Path(os.devnull)

    def idle_for(self):
        return self._idle


def test_open_in_browser_waits_for_disconnect_grace():
    server = FakeServer()
    opened = []
    ticks = {"n": 0}

    def fake_sleep(_):
        ticks["n"] += 1
        if ticks["n"] == 2:
            server.ever_connected.set()
        if ticks["n"] >= 4:
            server._idle = 100.0

    open_in_browser(server, grace=1.0, opener=opened.append, sleep=fake_sleep)
    assert opened and ticks["n"] >= 4


def test_open_in_browser_times_out_without_connection():
    server = FakeServer()
    with pytest.raises(TimeoutError):
        open_in_browser(server, first_connect_timeout=0.0, opener=lambda u: None, sleep=lambda s: None)


def test_open_window_falls_through_and_reports(monkeypatch):
    import framelab.launch as launch

    monkeypatch.setattr(launch, "find_chromium", lambda: None)
    monkeypatch.setattr(launch, "pywebview_available", lambda: False)
    monkeypatch.setattr(launch, "open_in_browser", lambda server: None)
    assert open_window(FakeServer(), order=("chromium", "pywebview", "browser")) == "browser"


def test_open_window_raises_when_everything_fails(monkeypatch):
    import framelab.launch as launch

    monkeypatch.setattr(launch, "find_chromium", lambda: None)
    monkeypatch.setattr(launch, "pywebview_available", lambda: False)

    def boom(server):
        raise OSError("no display")

    monkeypatch.setattr(launch, "open_in_browser", boom)
    with pytest.raises(RuntimeError, match="no display"):
        open_window(FakeServer())
```

`tests/test_api.py`:

```python
import threading

import pandas as pd
import pytest
from websockets.sync.client import connect

import framelab as fl
import framelab.api as api
from framelab.protocol import PROTOCOL_VERSION, decode_frame, encode_frame


@pytest.fixture
def ventas():
    return pd.DataFrame({"a": range(1000), "b": 0, "c": 0, "d": 0, "e": 0})


def fake_window(record):
    """Stand-in for open_window: acts as the frontend over the real WebSocket."""

    def _open(server, *, title="framelab", order=None):
        record["title"] = title
        origin = f"http://127.0.0.1:{server.port}"
        with connect(f"ws://127.0.0.1:{server.port}/ws?token={server.token}", origin=origin) as ws:
            ws.send(encode_frame({"v": PROTOCOL_VERSION, "id": "1", "type": "req", "method": "session.hello",
                                  "params": {"protocol_version": PROTOCOL_VERSION, "client": "ws"}}))
            record["hello"] = decode_frame(ws.recv(timeout=5))[0]["result"]
            ws.send(encode_frame({"v": PROTOCOL_VERSION, "id": "2", "type": "req", "method": "session.snapshot"}))
            record["snapshot"] = decode_frame(ws.recv(timeout=5))[0]["result"]
        return "fake"

    return _open


def test_explore_window_mode_serves_session_and_returns_it(monkeypatch, ventas, tmp_path):
    record = {}
    monkeypatch.setattr(api, "_open_window", fake_window(record))
    monkeypatch.setattr(api, "_static_dir", lambda: tmp_path)
    session = fl.explore(ventas, mode="window")
    assert session.names == ["ventas"]
    assert record["snapshot"]["roots"] == [{"id": "n1", "name": "ventas", "kind": "DataFrame", "shape": [1000, 5]}]
    assert "ventas" in record["title"]
    assert fl.last_session() is session


def test_explore_requires_pandas(monkeypatch):
    monkeypatch.setattr(api, "_open_window", lambda *a, **k: "fake")
    with pytest.raises(TypeError):
        fl.explore([1, 2, 3], mode="window")


def test_explore_requires_something():
    with pytest.raises(TypeError, match="at least one"):
        fl.explore()


def test_explore_inline_mode_displays_widget(monkeypatch, ventas):
    shown = []
    monkeypatch.setattr(api, "detect_env", lambda: api.Env.JUPYTER)
    monkeypatch.setattr(api, "_display", shown.append)
    session = fl.explore(ventas)
    assert len(shown) == 1 and session.widget is shown[0]
```

`tests/test_window_e2e.py` (E2E #1 — real Chromium, headless):

```python
import os
import threading
import time

import pandas as pd
import pytest

from framelab._paths import require_static
from framelab.launch.browsers import find_chromium
from framelab.launch.chromium import launch_app_window
from framelab.naming import RootSpec
from framelab.session import Session
from framelab.transport.dispatcher import Dispatcher
from framelab.transport.server import FramelabServer

pytestmark = pytest.mark.slow


@pytest.mark.skipif(find_chromium() is None, reason="no Chromium-family browser installed")
def test_real_browser_boots_the_frontend_and_close_is_detected():
    d = Dispatcher(Session([RootSpec("ventas", pd.DataFrame({"a": range(1000), "b": 0, "c": 0, "d": 0, "e": 0}), None)]))
    seen = []
    original = d.handle

    def spy(env, bufs):
        seen.append(env.get("method"))
        return original(env, bufs)

    d.handle = spy
    server = FramelabServer(d, require_static())
    server.start()
    redirect = server.write_redirect_file()
    window = launch_app_window(find_chromium(), redirect.as_uri(), extra_args=["--headless=new", "--disable-gpu"])
    try:
        deadline = time.monotonic() + 30
        while "session.snapshot" not in seen and time.monotonic() < deadline:
            time.sleep(0.05)
        assert "session.hello" in seen and "session.snapshot" in seen
        t0 = time.monotonic()
        window.close()
        window.wait(timeout=10)
        assert time.monotonic() - t0 < 5
    finally:
        window.close()
        redirect.unlink(missing_ok=True)
        server.stop()
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_launch.py tests/test_api.py -v` → FAIL (modules missing).

- [ ] **Step 3: Implement the launch package**

`src/framelab/launch/browsers.py`:

```python
"""Locate an installed Chromium-family browser (Chrome, Chromium, Edge, Brave)."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable

LINUX_NAMES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "microsoft-edge",
    "microsoft-edge-stable",
    "brave-browser",
    "brave",
)
MAC_APPS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)
WIN_EXES = ("chrome.exe", "msedge.exe", "brave.exe")
WIN_RELATIVE = (
    r"Google\Chrome\Application\chrome.exe",
    r"Microsoft\Edge\Application\msedge.exe",
    r"BraveSoftware\Brave-Browser\Application\brave.exe",
)


def _windows_candidates(exists: Callable[[str], bool]) -> str | None:
    try:
        import winreg
    except ImportError:
        return None
    for exe in WIN_EXES:
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
            try:
                with winreg.OpenKey(hive, key) as handle:
                    value, _ = winreg.QueryValueEx(handle, None)
            except OSError:
                continue
            if value and exists(value):
                return value
    for env_var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env_var)
        if not base:
            continue
        for rel in WIN_RELATIVE:
            candidate = os.path.join(base, rel)
            if exists(candidate):
                return candidate
    return None


def find_chromium(
    *,
    platform: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
    exists: Callable[[str], bool] = os.path.exists,
) -> str | None:
    override = os.environ.get("FRAMELAB_BROWSER")
    if override:
        if exists(override):
            return override
        return which(override)
    platform = platform or sys.platform
    if platform.startswith("linux") or platform.startswith("freebsd"):
        for name in LINUX_NAMES:
            path = which(name)
            if path:
                return path
        return None
    if platform == "darwin":
        return next((p for p in MAC_APPS if exists(p)), None)
    if platform == "win32":
        return _windows_candidates(exists) or which("msedge") or which("chrome")
    return None
```

`src/framelab/launch/chromium.py`:

```python
"""Open the UI as a chromeless Chromium 'app' window with a throw-away profile."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChromiumWindow:
    process: subprocess.Popen
    profile_dir: Path

    def wait(self, timeout: float | None = None) -> int:
        code = self.process.wait(timeout)
        shutil.rmtree(self.profile_dir, ignore_errors=True)
        return code

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(5)
        shutil.rmtree(self.profile_dir, ignore_errors=True)


def build_command(
    browser: str,
    target: str,
    *,
    profile_dir: Path,
    width: int = 1400,
    height: int = 900,
    extra_args: Sequence[str] = (),
) -> list[str]:
    return [
        browser,
        f"--app={target}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        f"--window-size={width},{height}",
        *extra_args,
    ]


def launch_app_window(
    browser: str,
    target: str,
    *,
    width: int = 1400,
    height: int = 900,
    extra_args: Sequence[str] | None = None,
) -> ChromiumWindow:
    profile = Path(tempfile.mkdtemp(prefix="framelab-profile-"))
    extra = (
        list(extra_args)
        if extra_args is not None
        else shlex.split(os.environ.get("FRAMELAB_BROWSER_ARGS", ""))
    )
    cmd = build_command(browser, target, profile_dir=profile, width=width, height=height, extra_args=extra)
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=sys.platform != "win32",
    )
    return ChromiumWindow(process, profile)
```

`src/framelab/launch/webview.py`:

```python
"""Optional native window through pywebview (pip install 'framelab[desktop]')."""

from __future__ import annotations

import importlib.util
import os
import sys
import threading


def pywebview_available() -> bool:
    return importlib.util.find_spec("webview") is not None


def _has_nvidia() -> bool:
    return os.path.exists("/proc/driver/nvidia/version")


def run_pywebview(url: str, title: str, width: int = 1400, height: int = 900) -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("pywebview must run on the main thread")
    if sys.platform.startswith("linux") and _has_nvidia():
        os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
    import webview

    webview.create_window(title, url, width=width, height=height)
    webview.start()
```

`src/framelab/launch/browser.py`:

```python
"""Last resort: a normal browser tab; the session ends when no tab stays connected."""

from __future__ import annotations

import time
import webbrowser
from collections.abc import Callable
from typing import Any


def open_in_browser(
    server: Any,
    *,
    first_connect_timeout: float = 120.0,
    grace: float = 60.0,
    poll: float = 0.25,
    opener: Callable[[str], Any] = webbrowser.open,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    redirect = server.write_redirect_file()
    opener(redirect.as_uri())
    start = time.monotonic()
    while not server.ever_connected.is_set():
        if time.monotonic() - start > first_connect_timeout:
            raise TimeoutError("the browser never connected to framelab")
        sleep(poll)
    while server.idle_for() < grace:
        sleep(poll)
```

`src/framelab/launch/__init__.py`:

```python
"""Open the framelab UI in the best available window, blocking until it closes."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

from .browser import open_in_browser
from .browsers import find_chromium
from .chromium import launch_app_window
from .webview import pywebview_available, run_pywebview

__all__ = ["default_order", "open_window"]


def default_order(platform: str | None = None) -> tuple[str, ...]:
    platform = platform or sys.platform
    if platform.startswith("linux"):
        return ("chromium", "pywebview", "browser")
    return ("pywebview", "chromium", "browser")


def open_window(server: Any, *, title: str = "framelab", order: Sequence[str] | None = None) -> str:
    errors: list[str] = []
    for method in order or default_order():
        try:
            if method == "chromium":
                browser = find_chromium()
                if browser is None:
                    continue
                redirect = server.write_redirect_file()
                try:
                    window = launch_app_window(browser, redirect.as_uri())
                    window.wait()
                finally:
                    redirect.unlink(missing_ok=True)
                if not server.ever_connected.is_set():
                    raise RuntimeError(f"{browser} exited before loading framelab")
                return "chromium"
            if method == "pywebview":
                if not pywebview_available():
                    continue
                run_pywebview(server.login_url, title)
                return "pywebview"
            if method == "browser":
                open_in_browser(server)
                return "browser"
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            errors.append(f"{method}: {exc}")
    raise RuntimeError("framelab could not open a window (" + "; ".join(errors or ["no method"]) + ")")
```

- [ ] **Step 4: Implement `src/framelab/api.py` and export it**

```python
"""Public entry point: fl.explore()."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any

from ._paths import require_static
from .env import INLINE_ENVS, Env, detect_env, resolve_mode
from .naming import resolve_root_names
from .options import registry
from .session import Session
from .transport.dispatcher import Dispatcher

__all__ = ["explore", "last_session"]

_last_session: Session | None = None


def _static_dir() -> Path:
    return require_static()


def _open_window(server: Any, *, title: str) -> str:
    from .launch import open_window

    return open_window(server, title=title)


def _display(obj: Any) -> None:
    from IPython.display import display

    display(obj)


def explore(*dfs: Any, name: str | None = None, mode: str | None = None, **named: Any) -> Session:
    """Open the framelab workbench for one or more DataFrames/Series."""
    global _last_session
    if not dfs and not named:
        raise TypeError("explore() needs at least one DataFrame or Series")
    frame = sys._getframe(1)
    try:
        specs = resolve_root_names(dfs, named, frame, explicit_name=name)
    finally:
        del frame
    session = Session(specs, registry)
    env = detect_env()
    resolved = resolve_mode(mode or registry.get("general.open_mode"), env)
    if resolved == "window" and env in INLINE_ENVS:
        warnings.warn(
            "opening a separate window from a notebook arrives in a later version; showing inline",
            stacklevel=2,
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

        title = f"framelab · {', '.join(session.names)}"
        server = FramelabServer(dispatcher, _static_dir(), title=title)
        server.start()
        try:
            _open_window(server, title=title)
        finally:
            server.stop()
    return session


def last_session() -> Session | None:
    return _last_session


# re-exported for tests that monkeypatch environment detection
__all__ += ["Env"]
```

`src/framelab/__init__.py`:

```python
"""framelab — explore, transform and plot pandas DataFrames without writing code."""

__version__ = "0.0.1.dev0"

from .api import explore, last_session  # noqa: E402
from .options import get_option, options, reset_option, set_option  # noqa: E402

__all__ = [
    "__version__",
    "explore",
    "get_option",
    "last_session",
    "options",
    "reset_option",
    "set_option",
]
```

Note: this makes `import framelab` import pandas (via `session`). Update `tests/test_packaging.py::test_sdist_installs_without_node` to install with deps from the local index cache instead of `--no-deps`: replace the pip command with `pip install -q --no-build-isolation`? No — keep `--no-deps` and change the check command to read the file path without importing the package:

```python
out = subprocess.run(
    [str(py), "-c", "import importlib.util, pathlib; spec = importlib.util.find_spec('framelab'); p = pathlib.Path(spec.origin).parent / '_static' / 'framelab.js'; print(p.is_file())"],
    check=True, env=env, capture_output=True, text=True,
)
```

- [ ] **Step 5: Run** `.venv/bin/python -m pytest tests/test_launch.py tests/test_api.py -v` → PASS. Then the slow ones: `.venv/bin/python -m pytest -m slow tests/test_window_e2e.py tests/test_notebook.py tests/test_packaging.py -v` → PASS.

- [ ] **Step 6: Manual check (spike S4 on Linux)** — create `spikes/s4-launcher/demo.py`:

```python
import pandas as pd

import framelab as fl

ventas = pd.DataFrame({"a": range(1000), "b": 0, "c": 0, "d": 0, "e": 0})
s = fl.explore(ventas)
print("returned", s)
```

Run `.venv/bin/python spikes/s4-launcher/demo.py`: a chromeless Chromium window titled "framelab · ventas" shows "ventas · 1000 × 5"; closing it prints `returned <framelab.Session …: ventas>` within ~1 s. Take a screenshot via the chrome-devtools MCP is not possible for this window — instead verify visually or with `grim` if available. Also run two scripts concurrently (both windows open independently). Record results in `spikes/s4-launcher/RESULT.md`. Windows/macOS: covered by the CI launcher smoke test (Task 15) — record "untested locally".

- [ ] **Step 7: Commit** ("Add window launcher chain and fl.explore() for scripts and notebooks").

---

### Task 13: Spike S3 — transport latency under GIL load

**Files:** `spikes/s3-load/run.py`, `spikes/s3-load/RESULT.md`

- [ ] **Step 1:** Write `spikes/s3-load/run.py`: build a `Session` with a 5M×30 numeric frame and a 5M-row object-dtype string column; `Dispatcher.register("spike.window", …)` returning `Reply({"offset": o}, [ipc_bytes])` where `ipc_bytes` is the Arrow IPC stream of `pa.Table.from_pandas(df.iloc[o:o+200])`; `Dispatcher.register("spike.heavy", …)` that starts a background thread running either (A) `df["s"].astype(str).str.upper()` on the object column (GIL-bound) or (B) `df.groupby(df["c0"] % 1000).sum()` (GIL-releasing) and returns immediately. Start `FramelabServer`, connect a websockets sync client (token query + origin), send 300 `spike.window` requests sequentially with random offsets: idle, during A, during B. Print p50/p95/max latency for each phase.
- [ ] **Step 2:** Run it; write `RESULT.md` with the table and the decision: p95 under load ≤250 ms → compute lane stays an in-process thread (M1a); otherwise → compute lane in a subprocess from M1a (update the spec).

---

### Task 14: Spike S2 — JupyterLab rendering and CSS isolation

**Files:** `spikes/s2-widget/check.ipynb` (generated), `spikes/s2-widget/RESULT.md`

- [ ] **Step 1:** Start JupyterLab headless: `.venv/bin/jupyter lab --no-browser --port 8899 --IdentityProvider.token=s2spike --ServerApp.root_dir=spikes/s2-widget &`.
- [ ] **Step 2:** Create `spikes/s2-widget/check.ipynb` with nbformat containing two cells each calling `fl.explore(...)` on different frames, plus a Markdown cell with a heading (to check host styles are untouched).
- [ ] **Step 3:** With the chrome-devtools MCP: open `http://localhost:8899/lab/tree/check.ipynb?token=s2spike`, run all cells, take a screenshot, run `evaluate_script` to (a) measure time from cell execution to the widget's `[data-testid=root-item]` appearing, (b) check computed styles of the notebook's Markdown heading are unchanged vs. a notebook without framelab, (c) confirm both widgets rendered independently, (d) right-click inside a widget and confirm JupyterLab's context menu does not open, (e) press `a`/`b` inside the widget and confirm no cells are inserted.
- [ ] **Step 4:** Record bundle size (`ls -l src/framelab/_static`), results and screenshot path in `RESULT.md`; stop JupyterLab. VS Code / Colab / JupyterHub: record "not testable locally — covered by design (comms only), revisit in M7".

---

### Task 15: CI skeleton

**Files:** Create `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: jdx/mise-action@v2
      - run: mise exec -- pnpm install --frozen-lockfile
        working-directory: frontend
      - run: mise exec -- pnpm typecheck
        working-directory: frontend
      - run: mise exec -- pnpm build
        working-directory: frontend
      - uses: actions/upload-artifact@v4
        with:
          name: static
          path: src/framelab/_static

  test:
    needs: frontend
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.11", "3.14"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: static
          path: src/framelab/_static
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install --upgrade pip
      - run: pip install -e . --group dev
      - run: python tools/gen_ts_types.py
      - run: git diff --exit-code frontend/src/generated
      - run: python -m pytest -m "not slow"

  package:
    needs: frontend
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: static
          path: src/framelab/_static
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - run: pip install -e . --group dev
      - run: sudo apt-get update && sudo apt-get install -y chromium-browser || true
      - run: python -m pytest -m slow tests/test_packaging.py tests/test_window_e2e.py tests/test_notebook.py -v
```

- [ ] **Step 2:** `.venv/bin/python -c "import yaml, sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` (install pyyaml ad hoc if missing) → no error.
- [ ] **Step 3: Commit + push**, then watch the run: `gh run watch --exit-status` (or `gh run list --limit 1`). Fix failures (typical: Windows path/permissions in `test_redirect_file_is_private…` → already skipped on win32; macOS/Windows `find_chromium` tests are platform-injected). Record the launcher smoke on Windows/macOS as covered by `test_launch.py` unit tests (real windows there are M8).

---

### Task 16: M0 close

**Files:** Create `docs/superpowers/spikes/2026-09-23-m0-spikes.md`; Modify `docs/superpowers/specs/2026-09-23-framelab-design.md` (only where spikes change decisions); Delete `spikes/`, `frontend/tests/scaffold/` (if any).

- [ ] **Step 1:** Write the consolidated spike report: one section per spike (S1–S11) with numbers, PASS/FAIL and the resulting decision.
- [ ] **Step 2:** Apply decision changes to the spec (e.g. compute lane in subprocess if S3 failed; grid switch if S1 failed; preview sampling threshold from S5; executed-form rules from S11).
- [ ] **Step 3:** `rm -rf spikes frontend/tests/scaffold`; run the full suite: `.venv/bin/python -m pytest && .venv/bin/python -m pytest -m slow` → all PASS; `ruff check . && ruff format --check .` → clean; `cd frontend && mise exec -- pnpm typecheck` → clean.
- [ ] **Step 4: Commit + push** ("Close M0: spike report, spec updates") and write the milestone summary for the user (what was done, how to try it: `python spikes-free demo`, e.g.

```bash
.venv/bin/python -c "import pandas as pd, framelab as fl; ventas = pd.DataFrame({'a': range(1000), 'b': 0, 'c': 0, 'd': 0, 'e': 0}); print(fl.explore(ventas))"
```

and what's next: M1a).
