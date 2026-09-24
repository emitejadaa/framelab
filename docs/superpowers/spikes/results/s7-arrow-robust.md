# Spike s7 — robust DataFrame window → Arrow IPC → flechette

**Verdict: PASS with one caveat.** Every column of every messy frame is displayable. Encode and decode meet their budgets on realistic frames. The worst-case "every awkward dtype at once" 50-column frame reaches the 20 ms encode budget only on warm windows (19.1 ms). Its first window takes about 30 ms because of the one-off per-column planning. Details and the implied design are below.

## Machine and versions

- Arch Linux x86_64, Intel i5-1235U with 12 logical CPUs, **frequency-capped: P-cores max 1.3 GHz, E-cores 0.9 GHz, turbo off** (`intel_pstate/no_turbo=1`), 7.5 GiB RAM. An uncapped laptop core would be roughly 2–3× faster.
- All final timings are **pinned to cpu0** (`taskset -c 0`, P-core 0, sibling cpu1 idle). Other spikes were loading the machine at the time. The first attempt's unpinned numbers (`out/bench_v1_small_CONTAMINATED_first_attempt.txt`, max 5.4 s) are discarded.
- Python 3.14.7, pandas 3.0.6, pyarrow 25.0.1, numpy 2.5.3 (repo `.venv`). Node v24.21.0 and pnpm 12.6.0 via mise. `@uwdata/flechette` 2.5.0 in `js/`.

## What was run

```bash
cd spikes/s7-arrow-robust
.venv/bin/python write_samples.py                 # v1 encoder: out/*.brief.arrow, out/*.safe.arrow, report.json
taskset -c 0 .venv/bin/python bench_encode.py small   # v1 timings            -> out/bench_v1_small_pinned.txt
taskset -c 0 .venv/bin/python bench_v2.py small       # v2 timings + *.v2/.v2safe.arrow -> out/bench_v2_small*.txt
taskset -c 0 .venv/bin/python bench_v2.py big         # 5M x 30 numeric       -> out/bench_v2_big.txt
.venv/bin/python prof_fallback.py | prof_v2_columns.py   # per-column costs   -> out/prof_*.txt
cd js && mise exec -- pnpm install
taskset -c 0 mise exec -- node decode.mjs ../out --filter .v2. --opts '{"useBigInt":true,"useDecimalInt":true}'
taskset -c 0 mise exec -- node decode.mjs ../out --filter .v2safe.          # default options
taskset -c 0 mise exec -- node warm.mjs '<opts>' ../out/<file>.arrow ...     # 200 warm decodes + 40-row viewport
taskset -c 0 mise exec -- node cold.mjs ../out/<file>.arrow '<opts>'         # fresh process, x3 each
```

### Frames (`frames.py`)

- **`messy_flat` (10k rows, 42 columns).** Nasty labels: int `0` twice (duplicate), tuple `('a', 1)`, `('solo',)`, naive and tz-aware Timestamp labels, `'dup'` twice, `3.5`, `None`, `np.nan`. Columns cover:
  - mixed-type object: int/str/float/None/date/bytes/bool
  - Period M/D (with NA), Interval int/float (with NA)
  - tz-aware datetimes (Europe/Madrid, UTC with NA) and `datetime64[ns]`
  - categoricals with int / Timestamp / ordered-float / tuple categories
  - nullable `Int64` / `Float64` / `boolean` with `pd.NA`
  - Decimal (and Decimal NaN)
  - list cells (int and mixed), dict cells (uniform and mixed), set cells, cells that are DataFrames
  - pandas 3 `str`, `string[pyarrow]`, `string[python]`
  - timedelta, complex, uint64 = 2^64−1, int64 = 2^62+1, float16, NaN/±inf, Sparse
  - `date` / `time` / `bytes` objects, `timestamp[s][pyarrow]`, `list<int64>[pyarrow]`, plus plain numeric columns.
- **`messy_wide_50`**: the same plus 8 float columns = **exactly 50 columns**. This is the timing target.
- **`multiindex`**: 3-level row MultiIndex (str, tz-aware datetime, unnamed int) × 2-level column MultiIndex with a duplicate pair.
- **`period_index_interval_label`**: a PeriodIndex for rows and an Interval column label.
- **`numeric_50`**: 100k × 50 (25 float64, 25 int64). **`strings_50`**: 10k × 50 pandas 3 `str`.
- **`numeric_5m_30`**: 5M × 30 (20 float64 + 10 int64, 1144 MiB).
- Edge cases: an empty window (offset == len) and a frame with 0 columns.

## Encoders

- **v1, `encoder.py` (as the brief specifies).** For each column: `pa.array(series, from_pandas=True)`. On an exception, or when the policy rejects the type, it falls back to text with the reason in `fallback`. Fields are named `c0…cN` and index levels `i0…iK`. Schema metadata key `framelab` holds JSON: `{offset, nrows_total, ncols_total, column_nlevels, columns:[{text, literal, dtype, fallback}], index:[…]}`. The stream is written with `pa.ipc.new_stream`. Two policies:
  - `brief`: keep whatever pyarrow produced.
  - `safe`: also force text for Period/Interval extension types, Decimal, and int64 beyond ±2^53.
- **Text fallback is NOT `series.astype(str)`**, because measured on one 1000-row window:
  - a column of 1×1 DataFrames: `astype(str)` takes **2 704 ms**;
  - 100k-element list cells: **135 ms per 20 cells** (≈ 6.8 s per window).

  Instead it uses a null-preserving bounded formatter: `reprlib` limits for containers, `"DataFrame r×c"`, 200-character cap, and a 5 ms/column time budget after which cells show `<TypeName>`. This costs 3.7 ms and 6.4 ms respectively (`out/astype_str_nested_df.txt`).
- **v2, `encoder_v2.py` (proposed).** A `WindowEncoder` per root frame. It **plans every column once** (first window) and caches the strategy by position, reusing it while scrolling:

  | strategy | used for | cost per 1000 cells |
  |---|---|---|
  | `native` | pyarrow-convertible columns. Object columns also cache their inferred Arrow type: Decimal 2.2 → 0.5 ms, dict→struct 0.87 → 0.28 ms. If a later window needs a wider type it re-infers. | |
  | `dense` | Sparse → `to_dense()` | 0.07 ms instead of 1.8 ms fallback |
  | `cat_str` | categoricals whose categories Arrow cannot hold (tuples) → dictionary\<str\> | 0.11 ms instead of 5.4 ms |
  | `text_fast` | pandas 3 `astype(str)` (vectorized, keeps NA as null), only when a type probe (`set(map(type, values))`, 0.04 ms) shows every cell type has a cheap, bounded `str`. Also used for Period (always text: its Arrow form is a bare ordinal) and complex. | |
  | `text_bounded` | the bounded formatter, with a C-speed `str()` fast path for small flat containers (≤16 scalar items) | 1.4 ms for list/dict columns instead of 4–6 ms |

  Columns are read with `DataFrame.items()` (`_ixs`), which is 2× cheaper than `iloc[:, j]`. Int64 values beyond 2^53 and Decimals stay native and are decoded exactly in JS with `{useBigInt: true, useDecimalInt: true}`. Alternatively, `js_safe=True` stringifies them in Python.

## Encode results: 1000-row windows, pinned to one core at 1.3 GHz

Cold is a fresh encoder (plans the columns), median of 5. Warm is a cached plan while scrolling through different offsets, median / p95 of 100 runs.

| frame (cols) | v1 brief | v1 safe | v2 cold | **v2 warm median / p95** | v2 js_safe warm | text-badged cols (v2) |
|---|---|---|---|---|---|---|
| messy_wide_50 (50) | 45.5 ms | 68.8 ms | 29.9–31.4 ms | **19.06 / 20.2–20.6 ms** | 20.9 / 22.3 ms | 6 (js_safe: 10) |
| messy_flat (42) | — | — | 29.4–30.0 ms | **18.3–18.4 / 19.6–19.8 ms** | 20.2 / 21.6 ms | 6 |
| numeric_50 (50) | 7.7 ms | 9.0 ms | 6.0–6.3 ms | **4.3 / 4.7–8.0 ms** | 4.3 / 4.7 ms | 0 |
| strings_50 (50, pandas 3 str) | 7.2 ms | 7.6 ms | 5.8–7.2 ms | **4.6 / 5.0–8.5 ms** | 4.6 / 5.0 ms | 0 |
| multiindex (6 + 3 index levels) | 5.1 ms | 5.4 ms | 4.9–5.3 ms | **3.9 / 4.3 ms** | 3.9 / 4.5 ms | 1 |
| **numeric_5m_30 (30)**, offsets 0 … 4 999 000 | — | — | 4.2 ms | **2.84 / 3.38 ms** (max 4.6) | — | 0 |

The 5M × 30 frame took 1.7 s to build (RSS +1147 MiB). Encoding windows at offsets 0 to 4 999 000 added only **+3.4 MiB RSS**: slicing does not copy the frame. Window sizes (IPC bytes, 1000 rows):
- numeric 50 columns: 418 KB
- strings 50 columns: 888 KB
- messy 50 columns: 446 KB
- 5M × 30: 254 KB

Where the messy warm 19 ms goes (`out/prof_v2_columns.txt`, sum of per-column medians 17.0 ms):
- the nested-DataFrame column: 3.6 ms (runs into its budget)
- list/dict text: 1.4 ms × 2
- complex: 1.3 ms
- Period text: 0.8 ms × 2
- Decimal: 0.4–0.6 ms
- column access across the 50 columns: 2.4 ms
- every native column: ≤ 0.33 ms

## Decode results: flechette 2.5.0, Node 24, pinned

| file (rows × fields) | warm decode median / p95 (200 runs) | cold decode, fresh process (x3) | 40-row viewport read, warm / cold |
|---|---|---|---|
| messy_wide_50.v2 (1000×51), bigint opts | **0.67 / 3.8 ms** | 10.6–11.2 ms | 0.46 / 7.0–9.0 ms |
| messy_wide_50.v2safe (1000×51), defaults | 0.63 / 3.6 ms | 10.8–11.2 ms | 0.55 / 7.2–7.4 ms |
| numeric_50.v2 (1000×51) | 0.26–0.38 / 0.57–3.3 ms | 7.8–8.3 ms | 0.11–0.25 / 1.0–2.4 ms |
| strings_50.v2 (1000×51) | 0.30–0.31 / 0.45–0.53 ms | 7.4–7.6 ms | 1.2 / 7.1–9.7 ms |
| numeric_5m_30_last.v2 (1000×31) | 0.24 / 0.27 ms | 6.4–6.5 ms | 0.09 / 1.9 ms |
| multiindex.v2 (500×9) | 0.08 / 0.10 ms | — | 0.10 ms |

The cold numbers are the first `tableFromIPC` call of a fresh process, before JIT warm-up. The one-time `import('@uwdata/flechette')` adds a further **12.3–15.0 ms**. Occasional GC pauses reached a max of 14–23 ms across 200 warm decodes. Reading every one of the 50k cells (`col.at(i)` on all of them) takes 11–38 ms. A grid never does that; it reads only the viewport.

## Displayability: every column, every file

With `tableFromIPC(bytes, {useBigInt: true, useDecimalInt: true})` over all 9 `*.v2.arrow` files, and with default options over all 5 `*.v2safe.arrow` files, **0 columns threw** on any row. The values for rows 0 and 1 of every column are in `out/decode_v2_bigint.txt`. How flechette carries each awkward dtype (v2):

| pandas dtype | Arrow → JS value | display note |
|---|---|---|
| object mixed (int/str/float/date/bytes/bool) | text_fast → LargeUtf8 `"1"`, `"a"` | badge (fallback) |
| period[M] / period[D] (+NA) | text `"2000-01"`, `"2000-01-02"`, null | no badge |
| interval[int64/float64, right/left] (+NA) | Struct `{left, right}` | closed side from `dtype` in metadata |
| datetime64 tz / naive, ns / us / s | Timestamp → epoch-ms number (tz in type) | format with the tz from the Arrow type |
| category int / Timestamp / float | Dictionary\<Int64 / Timestamp / Float64\> | native |
| category with tuple categories | Dictionary\<Utf8\> `"(1, 'a')"` | no badge |
| Int64 / Float64 / boolean with pd.NA | Int64 / Float64 / Bool, NA → null | native |
| Decimal | Decimal128(p,s) → **scaled BigInt** `1100n` (s=3) | exact; format with the scale |
| uint64 2^64−1, int64 2^62+1 | **BigInt** (throws `BigInt exceeds integer number representation` without `useBigInt`) | exact |
| list[int], set[int], `list<int64>[pyarrow]` | List\<Int64\> → arrays | native |
| list mixed, dict mixed, DataFrame cells | text_bounded `"[1, 'a']"`, `"{'a': 'x'}"`, `"DataFrame 1×1"` | badge |
| dict uniform | Struct `{a, b}` | native |
| complex | text `"(1+1j)"` | badge |
| Sparse[int64] | dense Int64 | native |
| date / time objects | Date (ms) / Time64[us] (BigInt µs) | native |
| bytes | Binary (Uint8Array) | render as hex / escaped |
| timedelta64[s] | Duration[s] (BigInt with useBigInt) | native |
| float16, NaN/±inf | Float16 / Float64. NaN arrives as **null** because `from_pandas=True` maps NaN → null | NaN vs NA is lost |
| pandas 3 `str`, `string[pyarrow]` / `string[python]` | LargeUtf8 / Utf8 | native |

With the **v1 `brief` policy and default decode options**, flechette decodes but shows wrong or unusable values:
- Period arrives as a bare Int64 ordinal (`360`).
- Decimal arrives as an inexact float (`-2.3449999999999998`).
- The two int64/uint64 columns beyond 2^53 **throw on every row** (2 error columns per messy file).
- Complex, Sparse, tuple categories and mixed objects fail in pyarrow itself (see `out/report.json`).

**Labels**: `literal` round-trips with `eval(literal, {"pd": pd, "np": np}) == label` and the same type for **51/51** labels: int, duplicate, tuple, 1-tuple, naive and tz-aware Timestamp, float, None, NaN, MultiIndex tuples, index names, Interval. The Interval label needed a `pd.Interval(...)` case; a bare `repr` gave `Interval(...)`, which does not evaluate. `text` gives the display strings (`"a / 1"` for tuples, ISO format for Timestamps).

## PASS / FAIL per criterion

| criterion | result |
|---|---|
| Every column displayable (native or string fallback) | **PASS**: 0 undisplayable columns across 14 decoded files (v2 + bigint/decimal options, or v2safe + defaults). v1 `brief` + default options would FAIL (throws for int64 > 2^53; Period/Decimal values misleading). |
| 1000×50 window encode < 20 ms (Python) | **PASS on realistic frames**: numeric 4.3 ms, strings 4.6 ms, 5M×30 2.8 ms, first window ≤ 7.2 ms. **Worst-case messy frame is borderline**: v2 warm 19.1 ms (p95 20.2–20.6), first window 30 ms (FAIL), v1 as briefed 45–69 ms (FAIL). All on a core capped at 1.3 GHz. |
| 1000×50 decode < 10 ms (Node) | **PASS**: warm median 0.26–0.67 ms, p95 ≤ 3.8 ms. The first decode in a fresh process is 6.4–11.2 ms (messy 1000×51: 10.6–11.2 ms, once per page load) plus a one-off 12–15 ms module import. |

## Decision for framelab

1. **Keep Arrow IPC stream + flechette** for grid windows, with positional field names `c0…cN` and `i0…iK` and a `framelab` JSON metadata entry holding text, literal, dtype, strategy and fallback for each column.
2. **Adopt the v2 encoder design**, not the literal brief:
   - Cache a per-column plan per root frame (invalidate when the node's frame changes).
   - Map Sparse to dense.
   - Map categoricals with unconvertible categories to dictionary\<str\>.
   - Send Period as text, and complex as text.
   - Keep Interval native as a struct, with `closed` taken from the dtype.
   - Choose object-column text with a type probe: vectorized `astype(str)` when every cell type is cheap, otherwise the bounded formatter.
   - **Never use plain `astype(str)` on object columns**: 2.7 s per window for DataFrame cells.
3. **Frontend decodes with `{useBigInt: true, useDecimalInt: true}`** and a type-aware cell formatter covering:
   - bigint → `toString`
   - Decimal: scaled bigint plus the scale from the Arrow type
   - Timestamp: ms plus the tz from the type
   - Date (ms), Time64 (µs bigint), Duration (bigint)
   - Interval struct plus `closed` from the metadata dtype
   - List/Struct → compact JSON
   - Binary → escaped

   (The fallback alternative, `js_safe=True`, stringifies big ints and decimals in Python for about +2 ms of encode; not needed.)
4. **Badge** (the "shown as text" flag) only columns that Arrow cannot carry: mixed objects, containers, complex, objects. Period, stringified categories and densified Sparse are not failures.
5. **Generated code must address duplicate labels positionally** (`df.iloc[:, j]`). `literal` is safe to paste only for unique labels. Keep a label → literal whitelist (int, float incl. nan/inf, str, None, bool, Timestamp ± tz, Period, Interval, tuples of these). For anything else fall back to positional access.
6. **Performance budget.** Typical frames cost 3–7 ms per 1000×50 window on this capped core, so no action is needed. For wide frames full of awkward dtypes, stay within 20 ms by (a) encoding only the visible column range plus a margin, rather than all columns, or (b) using smaller row windows (e.g. 500). The first-window planning cost (≈ +11 ms for the messy frame) is paid once per node. Note that NaN and NA both become null (Arrow `from_pandas`). If the grid must distinguish NaN from NA, send a separate validity/NaN flag. This was not needed for display.

## Files

- `frames.py`: builds the messy frames
- `encoder.py`: v1, the brief as written, with `brief`/`safe` policies and label helpers
- `encoder_v2.py`: the proposed planned encoder
- `write_samples.py`, `bench_encode.py`, `bench_v2.py`, `prof_fallback.py`, `prof_v2_columns.py`: sample writers, benchmarks and profilers
- `js/decode.mjs`: decodes, times and checks every cell of every column
- `js/warm.mjs`, `js/cold.mjs`: steady-state and fresh-process decode timings
- `out/*.arrow`: sample windows, in `.brief`, `.safe`, `.v2` and `.v2safe` variants
- `out/report.json`, `out/report_v2.json`: per-column outcome reports
- `out/*.txt`: raw outputs of every measurement quoted above
