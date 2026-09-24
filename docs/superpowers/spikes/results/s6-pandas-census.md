# s6-pandas-census — RESULT

**Question.** Can framelab auto-generate operation forms for pandas 3 using only introspection: `inspect.getattr_static`, `inspect.signature`, annotations resolved against `pandas._typing`, and numpydoc as a fallback? Pass criterion from the brief: **≥80 % of parameters overall map to a concrete widget.**

**Verdict: PASS.** Overall coverage is **89.8 %**. Coverage of named parameters is **98.3 %**. Build auto-forms as planned.

## Environment

- Machine: Arch Linux x86_64 (kernel 7.2.3), Intel i5-1235U with 12 threads, 7.5 GiB RAM. Other spikes were running in parallel, so the timings are noisy.
- Software: Python 3.14.7, pandas 3.0.6, numpy 2.5.3, numpydoc 1.11.0 (already present in the project venv; nothing was installed).

## What was run

```bash
cd /home/tejada/Desktop/plotExp/spikes/s6-pandas-census
MPLCONFIGDIR=<scratch> ../../.venv/bin/python census.py                 # -> census.json, census_output.txt
MPLCONFIGDIR=<scratch> ../../.venv/bin/python census.py --no-numpydoc   # -> census_no_numpydoc.json, census_output_no_numpydoc.txt
for i in 1 2 3; do ../../.venv/bin/python time_static.py; done           # cold-process timing
for i in 1 2 3; do ../../.venv/bin/python time_static.py --no-numpydoc; done
```

`census.py` is a single throwaway file (about 900 lines). It works in five steps:

1. **Targets.** Twelve targets are introspected on their runtime classes:
   - `DataFrame`, `Series`, `Index`
   - `DataFrameGroupBy`, `SeriesGroupBy` (from `head(0).groupby("c")`)
   - `DatetimeIndexResampler`, `Rolling`, `Expanding`, `ExponentialMovingWindow`
   - `.str`, `.dt`, `.cat`, taken from a tiny frame's `head(0)` with real `str`, `datetime64` and `category` dtypes
2. **Member classification.** Each public member is classified with `getattr_static` as one of: method, classmethod/staticmethod, property-like (property / AxisProperty / cache_readonly / other descriptors) or `Accessor`. Private members are dropped. A member counts as deprecated, and is dropped, only when the `.. deprecated::` marker comes **before the first numpydoc section**.
3. **Parameter types.** For each parameter:
   - Read the signature with `inspect.signature(f, annotation_format=annotationlib.Format.STRING)`.
   - Parse the annotation string with `ast`, and resolve names against the function's globals, then `pandas._typing`, `typing`/`collections.abc`, top-level `pandas` names, `pandas.api.typing`, `np`/`npt`/`lib`, and builtins.
   - Expand aliases (`TypeAliasType`), TypeVars (bound or constraints) and `Literal` values, which become enum choices.
4. **Widget kind.** Each parameter gets a widget kind by applying these rules in order:
   1. Annotation atoms mapped to kinds, including a table of `pandas._typing` alias names such as `Axis→axis`, `Frequency→freq`, `IndexLabel→labels`, `AggFuncType→func` and `Renamer→dict`.
   2. The `numpydoc.docscrape.NumpyDocString` type line, used either as a fallback or to upgrade a plain `str` to an enum. `{...}` choice sets are read with `ast.literal_eval` after stripping RST markup.
   3. The Python type of the default value.
   4. Name context: `by`/`subset`/`on`/... become `column(s)` on column-bearing owners, and `*value` names typed as `Hashable` become `scalar`.
   5. A last-resort name table.
5. **Runtime probes.** Probes run on a 4-row frame:
   - Every property/accessor is read.
   - Every method with no required arguments is called.
   - About 25 curated calls cover methods that need arguments (`update`, `insert`, `pop`, `eval`, `pipe`, `get_group`, ...).
   - Methods with `inplace=` are called with `inplace=True` when no other argument is required.
   - Mutation is detected by comparing the base object deep-copied before the call with the object after it (values, dtypes, index, attrs, flags).
   - `to_clipboard` is never called.

The widget kinds are the brief's list plus two extensions: **`scalar`** (a literal typed by the column dtype, e.g. `fill_value`) and **`values`** (a list literal, e.g. `isin(values)`). The "strict" column below counts those two as *not* concrete.

## Numbers — per class, with numpydoc (the build-time path)

| class | methods | cls/static | props | accessors | params | of which *args/**kwargs | **% concrete** | % concrete (named params only) | % strict (no scalar/values) | % type-only (no name rules) |
|---|---|---|---|---|---|---|---|---|---|---|
| DataFrame | 181 | 3 | 17 | 2 | 836 | 49 | **92.5** | 98.2 | 88.3 | 87.6 |
| Series | 172 | 1 | 23 | 7 | 654 | 53 | **90.2** | 98.2 | 83.5 | 89.0 |
| DataFrameGroupBy | 55 | 0 | 8 | 0 | 186 | 25 | **83.9** | 96.9 | 79.0 | 81.7 |
| SeriesGroupBy | 57 | 0 | 11 | 0 | 170 | 24 | **84.1** | 97.9 | 80.0 | 84.1 |
| Resampler | 27 | 0 | 7 | 0 | 50 | 12 | **76.0** | 100.0 | 72.0 | 76.0 |
| Rolling | 22 | 0 | 2 | 0 | 63 | 8 | **87.3** | 100.0 | 85.7 | 87.3 |
| Expanding | 22 | 0 | 2 | 0 | 61 | 6 | **90.2** | 100.0 | 88.5 | 90.2 |
| ExponentialMovingWindow | 9 | 0 | 2 | 0 | 25 | 4 | **84.0** | 100.0 | 84.0 | 84.0 |
| Index | 72 | 0 | 18 | 1 | 137 | 18 | **84.7** | 97.5 | 71.5 | 82.5 |
| `.str` | 57 | 0 | 0 | 0 | 104 | 0 | **100.0** | 100.0 | 95.2 | 100.0 |
| `.dt` (datetime) | 13 | 0 | 29 | 0 | 19 | 0 | **100.0** | 100.0 | 100.0 | 100.0 |
| `.cat` | 8 | 0 | 3 | 0 | 8 | 0 | **100.0** | 100.0 | 50.0 | 100.0 |
| **overall** | | | | | **2313** | 199 | **89.8** | **98.3** | 84.4 | 87.4 |

- **Excluded from the counts: 35 deprecated parameters** (forms would hide them): `copy` ×30, `method` ×2, `date_format` ×2, `verify_integrity` ×1.
- **Where the widget came from:** annotation 1611, numpydoc 395, annotation+name 36, annotation+numpydoc 16, numpydoc+name 14, name only 6, nothing 36, varargs 199.
- **Widget counts:** bool 568, int 266, unknown 235 (199 of them varargs), enum 204, str 202, axis 188, other-frame 90, float 82, dict 77, func 73, label 73, scalar 65, values 61, labels 39, freq 32, columns 30, dtype 15, column 13.
- **Enum choices:** 201 of 204 come straight from `Literal` annotations; numpydoc `{...}` sets supply 3 and upgrade another 16 parameters from a plain `str`.
- **Unions:** 123 named parameters (5.8 %) have more than one concrete candidate kind, for example `labels|values`, `int|values`, `other-frame|values`, `dict|enum`, `func|str`. The form needs a mode switch for these, so the catalog should store `candidates`, not just the chosen kind.
- **Nullable:** 601 parameters include `None`.
- **Dropped members:** private members, e.g. 214 on DataFrame. Only **1 member is deprecated at member level** in 3.0.6: `DataFrameGroupBy.corrwith`.
  - A naive check for `'.. deprecated::' in __doc__` wrongly drops 18 DataFrame members, including `merge`, `astype`, `rename` and `set_index`. Their markers belong to the deprecated `copy` **parameter**.
  - `Series.set_axis` needs an extra guard because pandas puts its `copy` note in the summary.

### Without numpydoc (the runtime fallback for members missing from the JSON)

| | overall % concrete | named only | strict | type-only |
|---|---|---|---|---|
| numpydoc (build) | 89.8 | 98.3 | 84.4 | 87.4 |
| signature + annotations only | **80.9** | 88.4 | 79.3 | 70.9 |

numpydoc matters most for the accessors and Index:

| target | with numpydoc | without |
|---|---|---|
| `.cat` | 100 % | 12.5 % |
| `.str` | 100 % | 74.0 % |
| `.dt` | 100 % | 78.9 % |
| Index | 84.7 % | 68.6 % |
| ExponentialMovingWindow | 84.0 % | 64.0 % |

(Without numpydoc, deprecated parameters can't be detected, so the parameter count is 2348.)

### Quality audit (a concrete kind is not automatically the right kind)

I reviewed two random samples of named, non-deprecated parameters by hand.

- **First sample** (seed 6, 80 params). It surfaced 3 bugs that inflated coverage. All are fixed in the numbers above:
  - `lib.NoDefault` expands to `Literal[no_default]` and produced a fake enum.
  - `fill_value: Hashable` mapped to a label picker.
  - `str | tuple[str, ...]` mapped to `labels`.
- **Final sample** (seed 2026, 100 params):
  - 99 got a concrete kind; the 1 unknown (`reindex(tolerance)`) is correctly unknown.
  - Of the 99: **93 are the right widget, 5 are usable but not ideal, and 1 is wrong**.
  - Usable but not ideal: `str.replace(repl)`→func instead of str; `pct_change(freq)` and `dt.to_period(freq)`→str instead of freq; `describe(exclude)`→values instead of a dtype multi-select; `to_excel(freeze_panes)`→values.
  - Wrong: `DataFrame.round(decimals)`→other-frame instead of int.
  - So about **94 % right, 99 % usable.** This is one reviewer's judgement.

### Timing (static pass over all 12 targets, about 2300 params, fresh process, 3 runs)

| path | static census | `import pandas` + script |
|---|---|---|
| with numpydoc | 608 / 716 / 1145 ms | 1.0–1.6 s |
| without numpydoc | 175 / 175 / 362 ms | 1.0–1.6 s |

A full run including all runtime probes took 5.7 s wall. That confirms the spec's plan: numpydoc at build time into a JSON file, and the runtime-only path is cheap enough for a lazy "Others" section.

## Parameters needing overrides (seed for the override table)

**Named unknowns: only 36 parameters, 17 distinct names, 17 distinct method names.** 33 class.methods have at least one named unknown:

| name | count | where / what it is |
|---|---|---|
| `ax` | 6 | plot/hist/boxplot → hide; the Ploter handles these |
| `tolerance` | 5 | reindex, reindex_like, get_indexer → freq or scalar |
| `fill_method` | 4 | pct_change; annotated `None`, a leftover deprecated parameter → hide |
| `na_value` | 3 | to_numpy (`object`) → scalar |
| `buf` / `con` / `nan_rep` / `filesystem` / `formatters` / `float_format` | 2/2/2/1/1/1 | writers → hide |
| `data` | 2 | `from_arrow` classmethod → not in forms |
| `fill_value` | 2 | `combine`, `GroupBy.shift` → scalar |
| `order`, `stable` | 1 each | `Series.argsort` numpy-compat `None` → hide |
| `filter_func` | 1 | `DataFrame.update` → func |
| `grouped` | 1 | `DataFrameGroupBy.boxplot` → hide |
| `sort_remaining` | 1 | `Index.sortlevel` → bool |

**Varargs: 199 parameters (135 `**kwargs`, 64 `*args`).** These account for most of the overall unknowns. They split into two groups:

- **Hide by a blanket rule (122 of 199, 61 %):** numpy-compat `*args/**kwargs` on reductions, `cum*`, `arg*`, `round`, `transpose`, `take` and `clip`; plot `**kwargs`; writer `**kwargs`.
- **Need a dedicated editor (77 of 199, across 11 method names plus `DataFrame.pivot_table(**kwargs)`):**
  - `DataFrame.assign(**kwargs)` → a "new columns" editor
  - `agg`/`aggregate(**kwargs)` → a named-aggregation editor, on every class
  - `apply` / `transform` / `map` / `pipe(*args, **kwargs)` → extra func arguments
  - `eval` / `query(**kwargs)` → an expression builder
  - `GroupBy.filter(*args, **kwargs)`
  - `GroupBy.resample(*args, **kwargs)` → freq

With a plain name→kind table, overriding the top 10 / 20 unknown names gives 91.1 % / 91.4 % overall. The rest is varargs, which need the rules above.

**Blanket rules the catalog needs:**

- Hide `inplace` on all 37 methods that have it (see below).
- Hide deprecated parameters.
- Hide numpy-compat varargs.
- Hide `ax` and writer I/O parameters.
- Treat `engine`/`engine_kwargs` as advanced.

**Estimated table size.** About 17 methods with unknowns, about 12 varargs editors, about 6 priority fixes from the audit, plus `GroupBy.__getitem__` and `GroupBy.nth`. That fits within the **~60-method override table** the spec plans.

## Members that return non-pandas objects or mutate (from actual calls on a 4-row frame)

**Probe coverage.** Of 831 members, 596 were probed:

- 343 returned pandas objects, 175 returned non-pandas objects, and 78 raised.
- The remaining 233 need arguments and were not probed, apart from the curated ones. The 2 `to_clipboard` members were deliberately skipped.
- Most DataFrame errors (31 of 44) are TypeErrors from reductions such as `mean`, `std`, `cumsum` and `abs` hitting the `str`/`category` columns. That is expected pandas 3 behaviour (framelab should suggest `numeric_only=True`), not an introspection failure.
- 3 errors are missing optional dependencies: `tabulate`, `xarray`, `lxml`.

### Mutation observed on the base object

- `DataFrame`: `insert` → None, `pop` → Series, `update` → None, `eval("z = a + b", inplace=True)` → None
- `Series`: `pop` → scalar, `update` → None
- Everything else called without `inplace` left the base unchanged. That includes all GroupBy, window and accessor methods probed, plus `pipe`, `apply`, `assign` and `set_axis`.

### `inplace=True` behaviour in pandas 3.0.6

37 methods take `inplace=`: 19 on DataFrame, 16 on Series, 2 on Index.

- **The return value is inconsistent, so it can't be used to detect in-place work.**
  - Returns **self**: `ffill`, `bfill`, `clip`, `Series.interpolate`, `Series.rename`.
  - Returns **None**: `dropna`, `drop_duplicates`, `reset_index`, `sort_index`, `sort_values`, `rename_axis`.
- **Partial mutation on error (confirmed separately).** On a frame with a `str` column, `DataFrame.interpolate(inplace=True)` fills column `b` and *then* raises `TypeError: Cannot interpolate with str dtype`. The frame stays modified.

### Non-pandas returns (preview policy input)

| class | members and what they return |
|---|---|
| DataFrame | `info()` → None and prints; `to_csv` / `to_json` / `to_html` / `to_latex` / `to_string` → str; `to_dict` → dict; `to_numpy` / `to_records` / `values` → ndarray; `to_parquet` → bytes; `items` / `iterrows` / `itertuples` → iterator; `boxplot` / `hist` → matplotlib; `plot` → PlotAccessor (callable Accessor); `style` → Styler; `shape` → tuple; `axes` → list; `attrs` → dict; `flags` → Flags; `loc` / `iloc` / `at` / `iat` → indexer objects; `empty` / `ndim` / `size` / `first_valid_index` / `last_valid_index` → scalar; `pipe` → whatever the function returns; writers needing a path (`to_excel`, `to_feather`, `to_hdf`, `to_pickle`, `to_sql`, `to_stata`, `to_iceberg`) not called; `to_clipboard` never called |
| Series | 66 non-pandas returns: every reduction (`sum`, `mean`, `std`, `quantile`, `idxmax`, `nunique`, `item`, ...) → scalar; `to_list` / `tolist` → list; `unique` → ndarray; `factorize` → tuple; `array` → ExtensionArray; `dtype` → numpy dtype |
| DataFrameGroupBy / SeriesGroupBy | `groups` → PrettyDict; `indices` → dict; `ngroups` → int; `nth` → **a property returning a callable, indexable `GroupByNthSelector`**, so it needs an override; `plot` → GroupByPlot |
| Index | 40 non-pandas returns: `isna` / `argsort` / `duplicated` → ndarray; `get_loc` → int; `slice_indexer` → slice; `slice_locs` / `sortlevel` / `factorize` → tuple |
| accessors | `str.cat()` → str; `dt.freq` / `dt.unit` / `dt.tz`, `cat.ordered` → scalar/None |

- Accessors found:
  - DataFrame: `plot`, `sparse`
  - Series: `cat`, `dt`, `list`, `plot`, `sparse`, `str`, `struct`
  - Index: `str`
- `DataFrame.style` is a plain property, not an Accessor.
- Runtime warnings: `DataFrame.to_json()` emits `Pandas4Warning`.

## Top-level functions (first argument, checked by actually calling each one)

| function | first param (annotation) | Series/1-D call | DataFrame as 1st arg |
|---|---|---|---|
| to_datetime | `arg` (`DatetimeScalarOrArrayConvertible \| DictConvertible`) | Series ✓ | ✓ (year/month/day frame) → Series |
| to_numeric | `arg` (unannotated) | Series ✓ | ✗ TypeError (1-D only) |
| to_timedelta | `arg` (`… \| Index \| Series`) | Series ✓ | ✗ TypeError |
| cut | `x` (unannotated) | Series ✓ | ✗ ValueError (1-D) |
| qcut | `x` (unannotated) | Series ✓ | ✗ ValueError (1-D) |
| crosstab | `index` (unannotated) | Series ✓ | ✗ ValueError |
| get_dummies | `data` (unannotated) | DataFrame ✓ | ✓ |
| concat | `objs` (`Iterable[Series \| DataFrame] \| Mapping[...]`) | list of frames ✓ | list only |
| merge | `left` (`DataFrame \| Series`) | ✓ | ✓ |
| melt | `frame` (`DataFrame`) | ✓ | ✓ |
| pivot_table | `data` (`DataFrame`) | ✓ | ✓ |
| wide_to_long | `df` (`DataFrame`) | ✓ | ✓ |

- **12 of 12 accept a pandas object first**, verified by calling them.
  - DataFrame first: `get_dummies`, `merge`, `melt`, `pivot_table`, `wide_to_long`, plus `to_datetime` on a frame of date parts.
  - Series / 1-D only: `to_numeric`, `to_timedelta`, `cut`, `qcut`, `crosstab`.
  - List of frames: `concat`.
- **Only 6 of 12 say so in the annotation.** 5 have no annotation at all, so the pd-functions table must be curated by hand.
- Their own parameters map to a concrete widget in **95 of 96 cases (99.0 %)**; the only miss is `pivot_table(**kwargs)`.
- A scan of all 62 top-level pandas functions: 13 are annotated as taking frames/Series first, 1 takes array-likes, 20 are readers and 28 are other.

## Pass/Fail

| criterion | result |
|---|---|
| ≥80 % of parameters overall map to a concrete widget | **PASS — 89.8 %** (named only 98.3 %; strict brief taxonomy 84.4 %; with no name rules 87.4 %; runtime path without numpydoc 80.9 %) |
| Per-class % reported | done (table above). Resampler is lowest at 76.0 %, entirely because of varargs: its named params are 100 % |
| List of parameter names needing overrides | done: 17 named-unknown names plus 12 varargs editor methods plus blanket rules |
| Non-pandas / mutating members listed, verified by real calls | done |
| Top-level functions with a DataFrame/Series first argument | 12/12 accept one; 6 take a DataFrame, 5 are 1-D only, `concat` takes a list |

## DECISION for framelab

1. **Build auto-forms as planned (M1b/M2b).** Introspection plus a small override table covers pandas 3. Keep the spec's pipeline: `getattr_static` → `inspect.signature` with `annotationlib.Format.STRING` → AST-walk the annotation against `pandas._typing` (don't use a bare `eval`: unresolved TYPE_CHECKING names must degrade per atom) → numpydoc at **build time only**.
   - numpydoc is worth about 9 points overall and is what makes `.str`, `.cat` and `.dt` work.
   - The runtime "Others" fallback without numpydoc still reaches 80.9 %.
2. **Widget taxonomy.**
   - Add `scalar` (a literal typed by dtype) and `values` (a list literal) to the brief's kinds.
   - Store `candidates`, `nullable` and `choices` per parameter; 5.8 % of parameters need a mode switch.
   - `Hashable` is ambiguous in pandas, so column vs label vs scalar needs name context.
3. **Override table (~60 entries holds).** Blanket rules plus specific entries:
   - Blanket: hide `inplace` / deprecated params / numpy-compat varargs / `ax` / writer I/O; `engine*` as advanced.
   - Special editors: `assign(**kw)`, named aggregation in `agg`, func extra args, `eval`/`query`, `GroupBy.filter`/`resample`, `GroupBy.nth`, `GroupBy.__getitem__`.
   - The 17 named-unknown methods and about 6 priority fixes (`round.decimals`→int, `str.replace.repl`→str, `pct_change.freq`/`dt.to_period.freq`→freq, `describe.include/exclude`→dtype multi-select).
4. **`mutates`: never pass `inplace=True`; force `inplace=False` or drop the parameter.**
   - In pandas 3.0.6, `inplace=True` returns self for some methods and None for others.
   - `interpolate(inplace=True)` mutates and *then* raises.
   - Mutators to block or rewrite: `insert`, `pop`, `update`, `eval(inplace)`, `__setitem__`. Rewrite them to `assign` / `drop` / `combine_first`-style forms, or run them on `copy(deep=False)` as the spec says.
5. **`returns` / `preview_policy`.** Map returns to policies:
   - Scalar, str, dict, list, tuple and ndarray → value node or inline value.
   - Iterators → excluded, or materialise with a cap.
   - matplotlib results and `plot` accessors → route to the Ploter, not the workbench.
   - `style` / Styler and writers → excluded, since export is handled separately.
   - Indexers (`loc`, `iloc`, `at`, `iat`) → the selection builder, not auto-forms.
6. **Deprecation.** Check only the docstring text before the first section, with the "This keyword" guard.
   - Member-level deprecations in 3.0.6: just `DataFrameGroupBy.corrwith`.
   - Parameter-level deprecations: 35, mostly `copy`, all hidden.
7. **pd functions.** Keep a hand-curated table: annotations are missing for 5 of the 12, and 1-D-only functions (`to_numeric`, `to_timedelta`, `cut`, `qcut`, `crosstab`) must be offered only on Series or column nodes.

## Caveats

- "Concrete" means a widget kind was assigned. The ~94 % ideal / 99 % usable figure comes from one reviewer judging one 100-parameter random sample.
- Name-context rules add 2.4 points (89.8 vs 87.4). Deciding column vs label relies on a name list (`by`, `subset`, `on`, `columns`, `id_vars`, ...).
- Return kinds for methods that need arguments come only from about 25 curated calls. 233 members were not probed, and mixed dtypes on the tiny frame make some reductions error.
- `.dt` was censused on datetime64 only. Timedelta and Period properties were not covered.
- Timings were taken on a loaded laptop with other spikes running in parallel, so treat them as orders of magnitude.

## Files

- `census.py` — the prototype. `--no-numpydoc` runs the runtime-only path.
- `time_static.py` — cold-process timing.
- `census.json` (1.3 MB) — full census: per class/member kind, per parameter annotation, resolved type, numpydoc type, widget, source, choices, candidates and deprecated flag, plus probe results, the overall summary, the top-level functions and the top-level parameter coverage.
- `census_no_numpydoc.json` — the same census for the runtime-only path.
- `census_output.txt`, `census_output_no_numpydoc.txt` — printed reports.

## Re-verification (2026-09-24)

- Re-ran `census.py` (with numpydoc) in a fresh process. Every count and percentage matched the first run exactly: 2313 params, **89.8 %** concrete, 98.3 % named, the same 17 unknown names. Only the timings changed: static census 589 ms (first run 813 ms), 5.0 s wall including probes (6.7 s with interpreter start). `census.json` and `census_output.txt` were regenerated from this run.
- Re-checked two claims independently:
  - `DataFrame.interpolate(inplace=True)` on a frame with a `str` column raises `TypeError` after filling `b` (`[1, 2, 3, 3]`).
  - `Series.ffill(inplace=True)` returns the Series itself, while `DataFrame.dropna(inplace=True)` returns `None`.
