# Spike s8 — caller-name detection and `detect_env` across Python 3.11–3.14 and run contexts

**Verdict: PASS.** Across 560 matrix runs plus 60 edge-case runs and 24 misattribution-probe runs, root naming never raised. It gave the ideal name in 540/560 matrix cases; the other 20 got a working name from the identity scan. `detect_env` was correct in every context.
The spike found one **correctness bug**: a wrong name when C code invokes `explore`. It also found two optional improvements. All three are listed under Decision below.

## Setup

- Machine: Arch Linux x86_64, Intel i5-1235U (12 logical CPUs, capped at 1.3 GHz P-core / 0.9 GHz E-core, turbo off), 7.5 GiB RAM.
- Interpreters: CPython 3.11.16, 3.12.14, 3.13.15 (`mise install python@3.11 python@3.12 python@3.13`, stored in `~/.local/share/mise/installs/python/`, outside the repo). Also CPython 3.14.7, the repo `.venv`.
- Throwaway venvs: `spikes/s8-varname-env/venv-3.1{1,2,3}`, each with pandas 3.0.6, executing 2.2.1, varname 1.0.0, ipython 9.17.1, ipykernel 7.3.0, nbclient 0.11.0. The repo `.venv` has the same versions.
- Code under test: `proto/naming.py` and `proto/env.py` are **verbatim copies** of `src/framelab/naming.py` and `src/framelab/env.py` (the Task 4 and Task 5 code as shipped). `proto/flproto.py` has an `explore(*dfs, name=None, mode=None, **named)` built like `api.py`: `sys._getframe(1)` → `resolve_root_names(...)` → `detect_env()`. It records the result as JSON instead of opening the UI.
- `proto/cases.py` holds 14 call shapes, written to be REPL-compatible: single, two positionals, multi-line call, `dfs[0]`, kwargs, positional + kwarg, `name=`, call expression, `*dfs`, a wrapper function, two calls on one line (2 cases), a list comprehension, and the same object passed twice.

## Commands

```bash
mise install python@3.11 python@3.12 python@3.13
~/.local/share/mise/installs/python/3.1X/bin/python3 -m venv spikes/s8-varname-env/venv-3.1X
venv-3.1X/bin/pip install pandas executing varname ipython ipykernel nbclient nbformat
.venv/bin/python spikes/s8-varname-env/run_matrix.py                       # shipped naming.py (560 records)
S8_NAMING=patched .venv/bin/python spikes/s8-varname-env/run_matrix.py     # naming_patched.py (560 records)
cd spikes/s8-varname-env/proto && S8_OUT=/dev/null <py> edge_cases.py      # + S8_NAMING=patched
cd spikes/s8-varname-env/proto && S8_OUT=/dev/null <py> misattribution.py  # + S8_NAMING=patched
```

`run_matrix.py` runs `cases.py` in 10 contexts on each interpreter:

| context | command |
|---|---|
| script file | `python cases.py` |
| python -c | `python -c "<source>"` |
| stdin script | `python - < cases.py` |
| REPL (python -i, piped) | `python -q -i < cases.py` (basic REPL) |
| REPL (python -i, pty) | `script -qec "python -q -i" /dev/null < cases.py` (real tty, so PyREPL on 3.13+) |
| IPython -c | `ipython -c "<source>"` |
| IPython (piped stdin) | `ipython < cases.py` |
| IPython (pty) | `script -qec "ipython ..." /dev/null < cases.py` (prompt_toolkit shell) |
| IPython file | `ipython cases.py` |
| Jupyter kernel | `proto/run_nb.py`: nbclient runs a 23-cell notebook, one cell per statement. The kernel runs the interpreter under test; the in-kernel `sys.executable` was checked for all 4 versions. |

## Results — shipped `naming.py` (Task 5 as implemented)

Each cell shows ideal names / cases and the path that produced them: `executing` (AST via `executing.Source.executing(frame).node` + `ast.unparse`) or `scan` (identity scan of `f_locals`/`f_globals`). **No case raised in any context.**

| context | detect_env | 3.11 | 3.12 | 3.13 | 3.14 |
|---|---|---|---|---|---|
| script file | script | 14/14 executing | 14/14 executing | 14/14 executing | 14/14 executing |
| python -c | script | 13/14 scan | 12/14 scan | 13/14 scan | 13/14 scan |
| stdin script | script | 13/14 scan | 12/14 scan | 13/14 scan | 13/14 scan |
| REPL (python -i, piped) | repl | 13/14 scan | 12/14 scan | 13/14 scan | 13/14 scan |
| REPL (python -i, pty) | repl | 13/14 scan | 12/14 scan | 13/14 scan | 13/14 scan |
| IPython -c | ipython-terminal | 14/14 exec 12 / scan 2 | same | same | same |
| IPython (piped stdin) | ipython-terminal | 14/14 exec 12 / scan 2 | same | same | same |
| IPython (pty) | ipython-terminal | 14/14 exec 12 / scan 2 | same | same | same |
| IPython file | ipython-terminal | 14/14 executing | same | same | same |
| Jupyter kernel (nbclient) | jupyter | 14/14 exec 12 / scan 2 | same | same | same |

Totals: 560 records, **540 ideal, 20 graceful fallback, 0 raised**. The full per-case tables are in `results/matrix.md`.

Fallbacks, all of which produce a valid name that exists in the user's namespace:
- `explore(dfs[0])` without source (-c, stdin, REPL) → `ventas`, not `dfs_0`. The scan finds the object's own variable, so generated code referencing `ventas` is correct.
- List comprehension on **3.12 only**, without source → `clientes`, not `x`. PEP 709 inlines comprehensions, so the loop variable is invisible in the module frame's `f_locals`. 3.13+ (PEP 667 `f_locals`) sees `x` again.
- In IPython and Jupyter, "two calls on one line" (`a = explore(ventas); b = explore(clientes)`) returns no node from `executing`. The scan still gives the ideal names.

Source availability behind the `scan` rows: `co_filename` is `<string>` for `-c`, `<stdin>` for stdin, and `<stdin>` for the REPL on 3.11/3.12. On 3.13+ the REPL uses `<stdin-N>` (piped) or `<python-input-N>` (PyREPL). These names are not in `linecache.cache`, so `executing` cannot see the source. IPython and ipykernel register their cells (`<ipython-input-…>`, `/tmp/ipykernel_*/…py`), so `executing` works there.

Timing of `resolve_root_names`: the first call per process (parses the caller's source) has a median of **7.8 ms** and a max of **30.4 ms**. Later calls have a median of **0.28 ms**, p95 1.5 ms, max 14.4 ms. The max came under CPU contention from other spikes.

## `detect_env` (Task 4 logic, copied verbatim)

| context | result | correct? |
|---|---|---|
| script file, `python -c`, stdin script | `script` | yes |
| `python -i` piped, `python -i` in a pty (PyREPL on 3.13+) | `repl` | yes |
| `python -i script.py` (script part, before the prompt) | `repl` | acceptable (both use window mode) |
| plain script that does `import IPython` (no shell) | `script` | yes |
| `ipython -c`, `ipython < file`, IPython in a pty, `ipython file.py` | `ipython-terminal` | yes |
| Jupyter kernel via nbclient | `jupyter` | yes (`VSCODE_PID` not set) |

It gave the same result on 3.11, 3.12, 3.13 and 3.14.

## Edge cases beyond the brief (`proto/edge_cases.py`, `proto/misattribution.py`, all 4 versions, identical results)

| call | shipped naming.py | patched |
|---|---|---|
| `sorted(one, key=explore)` / `max(one, key=explore)` where `one = [ventas]` | **`one` — WRONG** (names the list) | `ventas` (scan) |
| `list(map(explore, dfs))`, `next(map(explore, one))` | `df` | `ventas` (scan) |
| `ventas.pipe(explore)` | `obj` (a pandas-internal local) | `df` (pandas 3 pipes a `copy(deep=False)`, so no user variable holds it) |
| `functools.partial(explore)(ventas)` | `ventas` (executing) | `ventas` (scan) |
| `explore(ventas.head())`, `explore(ventas[["a"]])` | `df` | `df` |
| `explore(ventas["a"])` | `ventas_a`, src `ventas['a']` | same |
| `explore(dfs[i])` | `dfs_i`, src `dfs[i]` (depends on current `i`) | same |
| `explore(self.df)` in a method | `self_df`, src `self.df` | same |
| `explore(año)` | `año` | same |
| `next(explore(d) for d in dfs)` | `d` | same |
| `eval("explore(ventas)")`, `exec("r = explore(tabla)")` | `ventas` / `tabla` (scan) | same |
| `executing` not importable (`sys.modules["executing"] = None`) | scan: `ventas` | same |
| `explore(a, b, name="x")` | `ValueError` (intended) | same |

Cause of the wrong name: when C code (`sorted`, `max`, `map`) calls `explore`, `sys._getframe(1)` is the user's frame. `executing` then returns that frame's **current outer call** (`sorted(one, key=explore)`). Its argument count happens to match, so `one` was taken as the name.

## Patched variant (`proto/naming_patched.py`, diff in `proto/naming_changes.diff`)

1. **Callee check (bug fix).** `_call_node(frame, callee)` accepts the `executing` node only if `call.func` statically resolves to `explore`. It is a Name or dotted Attribute, looked up in `f_locals` → `f_globals` → builtins with `inspect.getattr_static`, so no code runs. It is then compared with `inspect.unwrap(...) is inspect.unwrap(explore)`. Otherwise the identity scan is used. This required adding `callee=` to `resolve_root_names`.
2. **3.13+ interactive source (optional).** When `co_filename` is `<...>` and `linecache` has no lines for it, the variant seeds `linecache.cache[filename]` from `linecache._getlines_from_code(frame.f_code)`. The REPL and `-c` register their source there on 3.13+. This is a **private** API, guarded with `getattr`.
3. **Skip pandas frames (optional).** In `explore`, walk `f_back` while `f_globals["__name__"]` starts with `pandas.`. This affects `df.pipe(explore)`.

Patched matrix: 560 records, **546 ideal, 14 fallback, 0 raised**. REPL (piped and pty) and `python -c` on 3.13/3.14 now reach 14/14 via `executing`. No row got worse. The cold first call was a median of 7.0 ms, max 21.1 ms; warm calls a median of 0.31 ms. Full tables: `results/matrix__patched.md`.

## Decision for framelab

- **The `naming.py` design (Task 5) is confirmed**: use `executing` + `ast.unparse` first, with the identity scan as fallback. It never raises, is exact wherever source exists (scripts, IPython, Jupyter), and falls back to a real, existing variable name elsewhere.
- **Required change:** add the callee check (patch item 1) so that a call from C code (`sorted/max/min(key=explore)`, `map(explore, …)`) cannot pick up the outer call's argument. It costs about 1 static lookup per call. Tests to add to `tests/test_naming.py`: `sorted([df], key=explore)` must not give the list's name; `functools.partial(explore)(df)` still gives `df`'s variable name.
- **Recommended (cheap):** skip `pandas.*` frames in `api.explore` before naming (patch item 3). Otherwise `df.pipe(fl.explore)` names the root `obj` after a pandas-internal local.
- **Optional:** seed `linecache` from `linecache._getlines_from_code` on 3.13+ (patch item 2). This gives exact names in the plain REPL and with `python -c`. It uses a private CPython helper, so keep it behind `getattr` and `try`. Without it the scan still gives correct, usable names.
- **`detect_env` (Task 4) needs no change.**
- Note for code generation: `source_expr` can contain a name-dependent subscript (`dfs[i]`). Treat it as informational (e.g. a `# from dfs[i]` comment), not as something to re-evaluate later.
- Performance: naming adds at most about 8 ms (median) to 30 ms on the first `explore()` call of a process on this CPU capped at 1.3 GHz, and under 1 ms after that. This is negligible compared with window startup.

## Files

- `proto/naming.py`, `proto/env.py`: verbatim copies of `src/framelab/{naming,env}.py`
- `proto/naming_patched.py`, `proto/naming_changes.diff`: the proposed changes
- `proto/flproto.py`, `proto/cases.py`, `proto/run_nb.py`, `proto/edge_cases.py`, `proto/misattribution.py`: the probe, the cases and the runners
- `run_matrix.py`: the driver. `results/*.jsonl` and `*.log` hold per-context raw records and stdout/stderr. `results/matrix.md` and `results/matrix__patched.md` hold the full tables. `results/cases_executed_py31X.ipynb` are the executed notebooks.
