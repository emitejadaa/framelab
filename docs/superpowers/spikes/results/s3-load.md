# S3 — transport latency under pandas load (Python 3.14.7, pandas 3.0.6, i5-1235U, 7.5 GiB)

Setup: FramelabServer + Dispatcher in-process; a WebSocket client asks for 200-row Arrow IPC
windows of a 5M-row table while a pandas job runs in another thread of the same process.

## run.py (5M x 30 floats + object column)
| phase | n | p50 | p95 | max |
|---|---|---|---|---|
| idle | 300 | 13.2 ms | 15.1 ms | 107 ms |
| during `s.astype(str).str.upper()` (object, 1.6 s) | 24 | 16.4 ms | 22.6 ms | 37.6 ms |
| during `groupby(...).sum()` incl. object column (38.2 s) | 76 | 15.6 ms | 23.8 ms | **36 827 ms** |

## ops.py — worst-case stall per operation (5M rows)
| operation | op time | p95 | max stall |
|---|---|---|---|
| groupby numeric sum | 0.46 s | 5.2 ms | 86 ms |
| groupby sum, all columns (incl. pandas-3 `str`) | 13.9 s | 5.3 ms | **13 430 ms** |
| sort_values | 4.6 s | 5.7 ms | 604 ms |
| merge m:1 | 0.47 s | 32 ms | 253 ms |
| str.upper (pyarrow str) | 0.15 s | 5.0 ms | 6.7 ms |
| str.upper (object) | 2.1 s | 122 ms | 390 ms |
| apply lambda (100k) | 0.05 s | 51 ms | 51 ms |
| describe | 5.2 s | 5.5 ms | 16 ms |
| value_counts (str) | 0.8 s | 5.1 ms | 7.1 ms |

## Verdict
- p95 criterion (<250 ms under load): **PASS** for every operation.
- Worst case: **FAIL** for aggregations that concatenate string columns (pandas 3 `numeric_only=False`):
  pandas' C code holds the GIL for the whole call, so every other Python thread (server, comms,
  renderer) stalls for 13–37 s. sort_values stalls up to 0.6 s.

## Decision
- Keep the compute lane as an in-process thread for M1a: a subprocess engine would have to copy
  every root (a 5M×30 frame is >1 GB) and move results back, doubling memory for the common case.
- The browser never freezes (rendering is independent); data requests are async: table blocks show
  skeletons and the inspector a spinner after ~150 ms, and the status bar shows the running op.
- Prevent the pathological case up front: the spec's "aggregation touches non-numeric columns"
  warning (suggest `numeric_only=True` / choose columns) becomes a guard before running.
- Re-measure in M8 benchmarks; if real sessions still show multi-second stalls, move the compute
  lane to a subprocess that owns the data (design kept open: Dispatcher is already transport-agnostic).
