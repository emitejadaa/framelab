# s1-glide: RESULT

**Question.** Can `@glideapps/glide-data-grid@6.0.4-alpha24` on React 19.3 handle 5,000,000 rows × 30 columns with
header histograms, context menus and a `.fl-root`-scoped portal, with two grids on one page? The criteria are no long
task over 50 ms while scrolling, no React 19 console errors, and a reachable last row.

**Verdict: PASS, with one required one-line patch.** Keep Glide, pinned exactly, and ship the pnpm patch described
under "Last row reachable". There is no need to switch to AG Grid Community.

## Setup

| | |
|---|---|
| Machine | Arch Linux x86_64 (kernel 7.2.3), Intel i5-1235U (12 threads; cpufreq showed a max of 1.3 GHz), 7 GB RAM, Intel ADL GT2 iGPU (Mesa). Other spikes ran in parallel, so the load average was 1.6 to 3.7. |
| Browser | `/usr/bin/chromium` 152.0.7977.82, **headless**, driven by `playwright-core@1.63.0`. No Playwright browsers were downloaded. The GPU runs used `--enable-gpu --ignore-gpu-blocklist`, which gives `ANGLE (Intel, Mesa Intel(R) Graphics (ADL GT2), OpenGL ES 3.2)`. The software runs used the default SwiftShader. |
| App | Vite 8.3.0, React 19.3.0 / react-dom 19.3.0 (`StrictMode`), TypeScript 7.0.2, `@vitejs/plugin-react` 6.1.1. Glide `6.0.4-alpha24` exact, with the peers `lodash@4.18.1`, `marked@16.4.2` and `react-responsive-carousel@3.2.23`. |
| Bundle (`pnpm build`) | `index.js` 528.85 kB min / 168.48 kB gzip, covering React, Glide and the app. Two lazy chunks (overlay editors, 3.6 kB and 16.0 kB) and 8.07 kB of CSS. |
| Page | Two `DataEditor` instances: A at 520 px and B at 260 px. Each has 5,000,000 rows × 30 columns from a deterministic hash-based `getCellContent` (f64, int and str columns), `rowMarkers="number"`, smooth scrolling on X and Y, and a `drawHeader` that draws a 20-bin histogram under every header. Right-click menus open through `onHeaderContextMenu`/`onCellContextMenu` and render with `createPortal` into `.fl-portal` inside `.fl-root`. `portalElementRef` points at that same `.fl-portal`. |
| Viewport | 1400×1000 CSS px at DPR 1, 1.5 and 2 (`deviceScaleFactor`). |

### Commands

```bash
cd spikes/s1-glide
mise exec -- pnpm install                          # patch applied from pnpm-workspace.yaml patchedDependencies
mise exec -- pnpm add -D --save-exact playwright-core@1.63.0
mise exec -- pnpm build                            # tsc --noEmit && vite build -> dist/
mise exec -- pnpm build:dev                        # development React build -> dist-dev/ (for console warnings)
cp -r dist dist-unpatched && sed -i 's/h<=0||h>=_-1?/h===0||h===_?/' dist-unpatched/assets/index-*.js  # revert the patch
.venv/bin/python -m http.server 8931 --bind 127.0.0.1 --directory dist           # + 8933 dist-dev, 8934 dist-unpatched
mise exec -- node tools/run-pw.mjs --url http://127.0.0.1:8931/ --label prod-gpu-dpr1 --dpr 1 --gpu --interact --trace --repeat 3
#   likewise: prod-gpu-dpr1.5, prod-gpu-dpr2, prod-sw-dpr1, prod-sw-dpr2 (--trace --repeat 3), dev-gpu-dpr1 (--interact),
#   unpatched-gpu-dpr1.5[-scrollbars], prod-gpu-dpr1.5-scrollbars (--scrollbars keeps the classic 15 px scrollbars)
.venv/bin/python tools/summarize.py <labels…>      # one-line summaries; the raw JSON is in results/<label>.json
```

`tools/run-pw.mjs` does the following:

- It injects `PerformanceObserver('longtask')` and `('long-animation-frame')` with `page.addInitScript` and collects
  `page.on('console'|'pageerror')`.
- It right-clicks and clicks with the real mouse and types with the real keyboard, all through Playwright.
- It records a CDP `Tracing` trace (`devtools.timeline`, `toplevel`, `v8.cpu_profiler`, …) during the first scroll run.
  `tools/analyze_trace.py` then lists DevTools `RunTask` events on the renderer main thread that took more than 50 ms.
- It runs the in-page scroll harness `window.__scrollTest()` (`src/harness.ts`). This is 605 rAF frames with one
  scroll write per frame. First come 180 frames × 60 px of wheel-like scrolling from the top. Then come 240 frames of
  "scrollbar drag" to row 4,999,000, with both grids moving in lock-step so every frame shows entirely new rows. Then
  another 180 frames × 60 px, and finally a jump to the bottom.
- It then checks the last row with trusted input: `Ctrl+End`, and `page.mouse.wheel` from 99.98 % down.
- `getCellContent` records the highest row index it was asked for (`window.__maxRowDrawn`). This proves that row
  4,999,999 was actually painted, not only that the visible-region callback reported it.

## Results

### 1. Long tasks while scrolling (criterion: none over 50 ms)

Each configuration ran 3 times with 605 frames per run. The first run of each configuration was the traced one and
also the first scroll after page load.

| Config (headless) | Frame Δ median / p95 / p99 / max (ms), per run | Frames >50 ms | **Long Tasks API >50 ms** | LoAF >50 ms (max) | DevTools trace `RunTask` >50 ms (traced run) |
|---|---|---|---|---|---|
| GPU, DPR 1 | 16.7/33.4/33.4/50.1 · 16.7/16.8/16.8/33.4 · 16.7/33.3/33.4/50 | 2 · 0 · 0 | **0 · 0 · 0** | 1 (55) · 0 · 1 (63) | none; p99 task 23.9 ms |
| GPU, DPR 1.5 | 16.7/33.4/33.4/100 · 16.7/33.3/33.4/33.4 · 16.7/33.3/33.4/50 | 2 · 0 · 0 | **0 · 0 · 0** | 2 (114) · 0 · 0 | none; p99 task 22.3 ms |
| GPU, DPR 2 | 16.7/33.4/50/100 · 16.7/33.4/33.4/50 · 16.7/33.4/33.4/50.1 | 4 · 0 · 1 | **0 · 0 · 0** | 4 (110) · 0 · 1 (55) | 1 × 64.9 ms wall with only **10 ms CPU** and no JS inside, so the thread was descheduled or waiting; heaviest JS task 44.1 ms; p99 24.3 ms |
| SwiftShader, DPR 1 | 16.7/33.3/33.4/66.6 · 16.7/33.3/33.4/50 · 16.7/33.3/33.4/50.1 | 2 · 0 · 1 | **1 (51 ms)** · 0 · 0 | 1 (59) · 0 · 0 | 1 × 55.1 ms wall / 31.3 ms CPU (React scheduler task, `FunctionCall` 50.7 ms); p99 22.2 ms |
| SwiftShader, DPR 2 | 33.3/50/50.1/83.4 · 16.7/33.3/33.4/50 · 16.7/33.4/33.4/50.1 | 13 · 0 · 1 | **1 (59 ms)** · 0 · 0 | 0 · 0 · 0 | none; p99 31.0 ms |

Two trace effects need explaining before reading the table:

- **Tracing-start artifact.** Every trace starts with one task of 148 to 234 ms made up of
  `V8.InvokeApiInterruptCallbacks`. That is the CPU profiler attaching, not app work, so the analyzer flags it and
  leaves it out.
- **The 65 ms DevTools-only tasks.** An earlier SwiftShader trace had 65.1 and 55.2 ms `RunTask`s that contained only
  about 5.5 ms of traced work. The Long Tasks API did not report them.

**Reading.** On the realistic configuration (hardware GPU, like the framelab Chrome `--app` window or a Jupyter
browser tab), the Long Tasks API recorded **0 long tasks in 9 of 9 runs** at DPR 1, 1.5 and 2, with a median frame of
16.7 ms. The only tasks above 50 ms were 51 and 59 ms. Both came from the software-raster runs, both during the first,
traced scroll, while CPU profiling was on and the box had a load average of about 3.6. On the GPU, the heaviest JS
frame task is about 42 to 44 ms. That happens in the drag phase, where every frame both grids repaint all their visible cells with brand-new text:
about 16 × 12 cells in A and 7 × 12 in B, so about 275 cells in total. Profile self time is dominated by `fillText` (1.6 to 2.3 s of 11 to 13 s traced).

This worst-case frame has little margin below 50 ms. It is still a **PASS**.

- Previous headful run (unexplained, not reproduced): a session used `chrome-devtools-mcp` 1.9.0 with a headful
  window, native DPR 1.5, on Hyprland (`results/mcp-PATCHED-run-dpr-native-headful.json`). Its scroll test logged
  long tasks of 104, 261, 189 and 213 ms.
- Same session, other runs: its unpatched headful run logged none, and its headful `run-prod-headful.json` logged one
  task of 66 ms.
- Not reproduced headless: 15 headless runs did not reproduce this. It is probably window, compositor or CPU
  contention, but that is not proven. Re-measure in the real window during M3.

Page load, which the criterion does not cover: three or four tasks of 54 to 244 ms at startup (module evaluation plus the
first mount of two grids under StrictMode). The first canvas appeared 693 to 927 ms after navigation.

### 2. React 19 console errors (criterion: zero)

| Build | Console messages during load, menus, overlay edit and 3 scroll runs |
|---|---|
| prod (`dist/`), 12 runs | **0 messages** |
| dev (`dist-dev/`, react-dom development, StrictMode) | 1 `info`: "Download the React DevTools…". **0 errors, 0 warnings** |

The app also wraps `console.error`/`console.warn` in-page (`window.__consoleErrors`), which stayed at `[]`. **PASS.**

### 3. Last row reachable (criterion: yes)

After the scroll harness, `lastVisibleRowA` was **4,999,999** in every patched run. `__maxRowDrawn` was
`{A: 4999999, B: 4999999}`, so both instances actually painted the last row. `Ctrl+End` and trusted mouse-wheel to
the bottom also both reach 4,999,999. `screenshot-prod-gpu-dpr1-last-row.png` shows row marker 5,000,000 in both
grids.

**This only holds with a patch, because stock 6.0.4-alpha24 has a bug at fractional DPR.**

- **Where:** `InfiniteScroller` (`internal/scrolling-data-grid/infinite-scroller.js`). For virtual heights above
  Chrome's roughly 33.5M px element limit, it scrolls 1:1 in DOM px. It only re-syncs to the exact end when
  `newY === scrollableHeight`.
- **What goes wrong:** at DPR 1.5 with a classic 15 px scrollbar, `clientHeight` is 505, and 505 × 1.5 is not a whole
  number of device pixels. At the bottom, Chrome reports `scrollTop = max + 1` (33,553,896 vs 33,553,895), so the
  equality never holds.
- **Effect:** wheel or scrollbar scrolling stops **774 rows short**, with a last visible row of 4,999,225
  (`results/unpatched-gpu-dpr1.5-scrollbars.json`). The earlier headful native-1.5 run stopped at 4,999,151
  (`results/mcp-unpatched/run-dpr-native-headful-UNPATCHED.json`). `Ctrl+End` and `scrollTo()` still work.
- **When it shows up:** with integral device pixels, it does not reproduce. That covers DPR 1, 1.25, 1.5 and 2 with
  scrollbars hidden (`unpatched-gpu-dpr1.5.json`, `unpatched-gpu-dpr1.25.json`, `results/mcp-unpatched/run-dpr-*.json`).
- **Fix:** `patches/@glideapps__glide-data-grid@6.0.4-alpha24.patch` changes one line (in both the ESM and CJS
  builds) to `newY <= 0 || newY >= scrollableHeight - 1`.
- **Result of the fix:** in the same scrollbars + DPR 1.5 setup, the patched build reaches 4,999,999 on every path
  (`results/prod-gpu-dpr1.5-scrollbars.json`). **PASS with the patch.**

### 4. Menus and portal inside `.fl-root`, and two instances (brief requirements)

- **Context menus**, tested with real right-clicks.
  - Targets: header c3 of grid A, cell (c5, row 4) of grid A, and header c1 of grid B.
  - Each click fired the correct callback, and the menu mounted **inside `.fl-portal` inside `.fl-root`**
    (`insideFlRoot: true`, `parentIsPortal: true` for all three).
  - Calling Glide's `preventDefault()` in the event args suppresses the browser's native menu (`defaultPrevented`
    true 3/3). The menu closes on mouse-leave.
- **Overlay editor.** `portalElementRef?: React.RefObject<HTMLElement>` **exists in 6.0.4-alpha24**.
  - Clicking cell (c2, r2) and pressing Enter opens `.gdg-clip-region` inside `.fl-portal` inside `.fl-root`, and
    `document.getElementById('portal')` is null.
  - Without the prop, Glide falls back to `#portal` and otherwise logs a `console.error`
    (`data-grid-overlay-editor.js:103`).
  - Typing and then pressing Enter fires `onCellEdited`. Caveat: when Enter came within 20 ms or less of the last
    keystroke, the edit was dropped (0/6 at 0 ms and 20 ms gaps, OK at 50 and 100 ms). Glide reads stale editor
    state. This does not matter for framelab's read-only table.
- **Glide writes to `document.body`**, outside `.fl-root`, in three places:
  - `color-parser.js` appends a permanent hidden `position:fixed` div to resolve colors with `getComputedStyle`.
  - A transient scrollbar-width probe.
  - A drag-image canvas, only when `isDraggable` is set.

  The consequence is that **theme values passed to Glide must be concrete colors**. A `var(--fl-…)` scoped to
  `.fl-root` would resolve against `<body>`.
- **Two instances.** Both grids are mounted, scroll in lock-step during the jump phase, and both paint row 4,999,999.
  A header right-click on grid B works.

Screenshots: `screenshot-prod-gpu-dpr1-{top,menu,overlay,last-row}.png` (the `dev-gpu-dpr1-*` ones are the dev
build). Raw JSON and gzipped traces are in `results/`. `results/mcp-unpatched/` and
`results/mcp-PATCHED-run-dpr-native-headful.json` come from the earlier session, which drove `chrome-devtools-mcp`
1.9.0 with `--executablePath /usr/bin/chromium` (`tools/mcp-driver.mjs`, `tools/run-s1.mjs`, `tools/dpr-bottom.mjs`).
Its conclusions match these runs.

## PASS/FAIL

| Criterion | Result |
|---|---|
| No long task >50 ms while scrolling top → row 4,999,000 → bottom | **PASS** on GPU (Long Tasks API 0 in 9/9 runs; DevTools trace: none with JS over 50 ms). Marginal on SwiftShader: 1 of 3 runs had a 51 or 59 ms task, in the traced, cold-JIT run under load. |
| Zero React 19 console errors | **PASS** (0 in prod, 0 errors or warnings in dev with StrictMode) |
| Last row reachable | **PASS with the patch.** Stock alpha24 FAILS by 774 rows at fractional device-pixel sizes (DPR 1.5 with scrollbars). |
| Menus and overlay portal inside `.fl-root`, two instances | **PASS** (`portalElementRef` supported) |

## Decision for framelab

1. **Keep Glide Data Grid `6.0.4-alpha24` (exact pin) for M3. Do not switch to AG Grid Infinite Row Model.** Keep the
   adapter boundary as planned.
2. **Ship the scroller patch.** Put `patches/@glideapps__glide-data-grid@6.0.4-alpha24.patch` in
   `frontend/patches/` and register it under `pnpm-workspace.yaml` → `patchedDependencies`. Add a regression check to
   the M3 Galata or Playwright smoke: DPR 1.5, visible scrollbars, wheel to bottom, assert row 4,999,999. Consider
   sending the fix upstream.
3. Mount **one PortalContainer inside `.fl-root`** and pass it to every grid through `portalElementRef`. Render the
   framelab context menus there with `createPortal`, and call `preventDefault()` in `onHeaderContextMenu` /
   `onCellContextMenu` so the native menu is suppressed (and in JupyterLab also keep `data-jp-suppress-context-menu`).
4. **Resolve theme tokens to concrete color strings before building the Glide `Theme`**, by calling
   `getComputedStyle(flRoot)` and re-resolving when the theme changes. Glide parses colors in a hidden div on
   `<body>`, where `.fl-root` CSS variables do not apply.
5. Budget: a full repaint of both grids, about 275 visible cells of new text, costs a p99 main-thread task of 22 to
   24 ms. The heaviest task was 42 to 44 ms, including GC, and the time is mostly `fillText`. The M3 `getCellContent` over Arrow blocks must stay allocation-light, with no per-cell string
   formatting beyond `displayData`, to keep the worst frame under 50 ms. Pre-format display strings when decoding
   blocks.
