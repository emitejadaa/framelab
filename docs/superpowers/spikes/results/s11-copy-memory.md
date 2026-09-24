# S11 — copy semantics and memory (pandas 3.0.6, 3M × 20 mixed frame, idle i5-1235U)

| operation | wall | RSS Δ | shared column buffers |
|---|---|---|---|
| `v.copy()` | 195 ms | +366 MB | 4/20 (only immutable Arrow str) |
| `v.copy(deep=False)` | 0.6 ms | +0.2 MB | 20/20 |
| `v2 = v.copy(); v2["c"] = …` | 135 ms | +390 MB | 4/20 |
| `v3 = v.copy(deep=False); v3["c"] = …` | 12 ms | +24 MB | 19/20 |
| `v.assign(c=…)` | 12 ms | +24 MB | 19/20 |

All 23 equality/isolation checks pass: every variant gives identical results, the original is never
touched (also after in-place edits on the derived results and after the user edits their own frame),
`to_numpy()`/`.values` are read-only under CoW.

**Decision (confirms spec P1):** show `v2 = v.copy()` + assignment, execute
`v2 = v.copy(deep=False)` + assignment (or `assign`) — 16× faster and ~15× less memory, provably equal.
Roots are frozen with `copy(deep=False)` (0.6 ms, no memory).
