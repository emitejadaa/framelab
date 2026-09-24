# s10-dnd-reactflow: RESULT

**Question.** Does `@xyflow/react@12.11.6` support the drag-and-drop design in the spec? That design uses React
Flow's own node drag for canvas nodes. Drops on external targets are detected by DOMRect hit-testing in
`onNodeDragStop`, then the node snaps back. Combining nodes uses `getIntersectingNodes`. A small pointer-events DnD
module is used only for external sources dragged into the canvas. The criterion is that all four cases, (a) to (d),
work at zoom 0.5 and 2.

**Verdict: PASS.** Every check passed at zoom 0.5, 1 and 2, at DPR 1 and 1.5. One UX issue matters (auto-pan drift
when dragging to targets outside the canvas), and a four-line mitigation fixes it.

## Setup

| | |
|---|---|
| Machine | Arch Linux x86_64 (kernel 7.2.3), Intel i5-1235U (12 threads), 7 GB RAM. Other spikes ran in parallel. |
| Browser | `/usr/bin/chromium` 152.0.7977.82, **headless**, driven by `playwright-core@1.63.0`. All input is trusted CDP mouse input through `page.mouse` (down, move with 20 to 25 steps, up), the same kind of events the chrome-devtools MCP `drag` tool produces. The MCP itself cannot start on this box because it looks for Chrome at `/opt/google/chrome`. |
| App | Vite 8.3.0, React 19.3.0 (`StrictMode`), TypeScript 7.0.2, `@xyflow/react` 12.11.6 (with `@xyflow/system` 0.0.82). Bundle: 406.44 kB JS min / 128.33 kB gzip, plus 15.41 kB CSS. |
| Page (viewport 1400×760) | A fake tab bar (Workbench, **Tabla**, **Ploter**; the last two are drop zones). A sidebar with 3 items that use pointer DnD. A React Flow canvas (about 983×518 px) with 6 nodes, 3 edges, `Background` and `Controls`, and `minZoom` 0.25 / `maxZoom` 4. To the right of the canvas are **two drop boxes outside it**. Below is a visible event log, and every event is also pushed to `window.__events`. A single `.fl-portal` sits inside `.fl-root` and holds the DnD ghost. |

### Commands

```bash
cd spikes/s10-dnd-reactflow
mise exec -- pnpm install && mise exec -- pnpm build          # tsc --noEmit && vite build -> dist/
.venv/bin/python -m http.server 8932 --bind 127.0.0.1 --directory dist
mise exec -- node tools/run-dnd.mjs --dpr 1   --label dpr1                                  # zooms 0.5,1,2
mise exec -- node tools/run-dnd.mjs --dpr 1.5 --label dpr1.5
mise exec -- node tools/run-dnd.mjs --dpr 1   --label dpr1-fix --url 'http://127.0.0.1:8932/?fix=1'   # auto-pan mitigation
mise exec -- node tools/shot-node-over-box.mjs                                               # mid-drag screenshot
.venv/bin/python tools/summarize.py dpr1 dpr1.5 dpr1-fix       # raw JSON in results/<label>.json
```

For each zoom, `tools/run-dnd.mjs` resets the graph and uses `setCenter` so the nodes under test are on screen. It
then drags with the real mouse and reads `window.__events`, `rf.getNode(id).position`, the viewport and DOM rects.

### How each case is implemented (`src/App.tsx`, `src/pointerDnd.tsx`)

- **(a)** Plain React Flow drag. `onNodeDragStop` logs a `move` when the pointer is inside the canvas and there is
  no intersection.
- **(b)**
  - At drag start: `onNodeDragStart` stores the start positions.
  - During the drag: `onNodeDrag` hit-tests `event.clientX/Y` against the DOMRect of every `[data-drop-zone]` and
    highlights the zone under the pointer.
  - On release: if the pointer is outside the canvas, `onNodeDragStop` hit-tests the same way, logs
    `drop-external {zone}`, and `setNodes` restores the start position.
- **(c)** `onNodeDragStop` calls `rf.getIntersectingNodes(node)` (partial overlap counts, which is the default), skips
  the nodes being dragged, logs `combine {target}`, and snaps the node back.
- **(d)**
  - Drag: `onPointerDown` calls `setPointerCapture`, with a 4 px threshold. The ghost is rendered with `createPortal`
    into `.fl-portal`.
  - Release: a DOMRect hit-test against the canvas, then `rf.screenToFlowPosition({x: clientX, y: clientY})` places a
    new node there.
  - Check: after two animation frames, the app measures the new node's DOM rect and logs how far its top-left corner
    is from the release point (`sidebar-drop-check dx/dy`).
  - Cancel: releasing outside the canvas logs `sidebar-cancel` and adds no node.

## Results

This table covers DPR 1. DPR 1.5 gave identical outcomes (`results/dpr1.5.json`). "Flow Δ" is how far the node
moved in flow units when the mouse moved 100 px right and 60 px down on screen.

| Check | zoom 0.5 | zoom 1 | zoom 2 |
|---|---|---|---|
| Pan (drag on empty pane by −90, −45 px) | viewport Δ = (−90, −45) ✔ | (−90, −45) ✔ | (−90, −45) ✔ |
| Wheel zoom (one notch) | 0.5 → 0.590 ✔ | 1 → 1.181 ✔ | 2 → 2.362 ✔ |
| **(a)** Node drag, screen (+100, +60) px | flow Δ (198, 118), expected (200, 120) ✔ `move` | (99, 59) / (100, 60) ✔ | (49.5, 29.5) / (50, 30) ✔ |
| **(b)** n2 → drop box 1 (Plotter axes) | `drop-external box:plotter`, highlighted during hover, **position restored exactly** ✔ | ✔ | ✔ |
| **(b)** n2 → drop box 2 (Inspector) | `drop-external box:inspector`, restored ✔ | ✔ | ✔ |
| **(b)** n3 → tab "Ploter" | `drop-external tab:ploter`, restored ✔ | ✔ | ✔ |
| **(b)** n5 → tab "Tabla" | `drop-external tab:tabla`, restored ✔ | ✔ | ✔ |
| **(c)** n4 dropped onto n5 (centre) | `combine target=n5`, n4 restored ✔ | ✔ | ✔ |
| **(c)** n4 edge overlapping n5 by about 10 px | `combine target=n5` ✔ | ✔ | ✔ |
| **(d)** sidebar `df_sales` → canvas (pane + 430, + 290) | flow (780, 500) = expected; node top-left vs pointer **(0, 0) px** ✔ | (390, 250), (0, 0) ✔ | (195, 125), (0, 0) ✔ |
| **(d)** same with the page scrolled 80 px | (780, 500), (0, 0) ✔ | ✔ | ✔ |
| **(d)** mid-drag state | ghost in `.fl-portal` ✔, inside `.fl-root` ✔, `hasPointerCapture(1)` ✔, ghost removed on drop ✔ | ✔ | ✔ |
| **(d)** release over drop box 2 (not the canvas) | `sidebar-cancel`, node count unchanged ✔ | ✔ | ✔ |
| Console (prod build) | 0 messages, 0 errors or warnings | | |

The (a) readings are 1 screen px short of the expected delta at every zoom, for example 99 instead of 100 px. That is
React Flow's drag start: the node starts moving at the first move past `nodeDragThreshold`. It does not matter here.

### Finding: auto-pan drifts the viewport during external drops

When a node is dragged to a target outside the canvas, React Flow's `autoPanOnNodeDrag` keeps panning. `calcAutoPan`
saturates while the pointer is beyond the pane edge. The node's flow position snaps back correctly, but the **viewport
has moved by 148 to 180 px horizontally** (drop boxes) or **by (23 to 113, 128 to 135) px** (tab bar) by the time of
release. The user therefore sees the graph jump.

- **The mitigation** (`?fix=1`):
  - During the drag: `onNodeDrag` sets `autoPanOnNodeDrag` to `false` while the pointer is outside the canvas. The
    xyflow auto-pan loop re-reads this prop every animation frame, so the change takes effect mid-drag.
  - On an external drop: `rf.setViewport()` restores the viewport saved in `onNodeDragStart`.
- **Result:** viewport drift is **(0, 0) in all 12 external drops** (4 targets × 3 zooms), and every other check
  still passes (`results/dpr1-fix.json`).

### Finding: the node is invisible outside the canvas

The node being dragged is clipped by the pane (`overflow: hidden`) once the pointer leaves the canvas. The user sees
only the cursor and the highlighted zone (`screenshot-node-over-dropbox-zoom2.png`). The product needs a ghost of the
node in the `.fl-root` portal while the pointer is outside the canvas.

Screenshots:

- `screenshot-dpr1-zoom{0.5,2}-ghost.png`: sidebar ghost over the canvas.
- `screenshot-node-over-dropbox-zoom2.png`: node dragged over drop box 1, with the box highlighted.
- `screenshot-after-snapback-zoom2.png`: after the snap-back.
- `screenshot-*-final.png`: the event log.

## PASS/FAIL

| Criterion | zoom 0.5 | zoom 2 | (zoom 1) |
|---|---|---|---|
| (a) normal node drag | **PASS** | **PASS** | PASS |
| (b) release over 2 external boxes and the tab bar, DOMRect hit-test in `onNodeDragStop`, snap back | **PASS** (4/4 targets) | **PASS** (4/4) | PASS |
| (c) node onto node with `getIntersectingNodes` | **PASS** (centre and partial overlap) | **PASS** | PASS |
| (d) pointer-events DnD sidebar → canvas (`setPointerCapture`, portal ghost, `screenToFlowPosition`) | **PASS**, 0 px error, also with the page scrolled | **PASS** | PASS |

These were also repeated at DPR 1.5, with all checks passing.

## Decision for framelab

1. **The spec's DnD split holds.** Canvas nodes use React Flow's own drag: `onNodeDragStart`/`onNodeDrag`/
   `onNodeDragStop`, with DOMRect hit-testing of external zones and tabs, snap-back through `setNodes`, and
   `getIntersectingNodes` for combining. External sources (sidebar → canvas, inspector column → Series, Plotter node
   list → axes) use the small pointer-events module: `setPointerCapture`, a ghost in the `.fl-root` PortalContainer,
   and `screenToFlowPosition`. No `@dnd-kit` is needed for either of these, as planned.
2. Add to the M2a canvas implementation:
   - Turn `autoPanOnNodeDrag` off while the pointer is outside the canvas.
   - Restore the viewport saved at drag start after an external drop or cancel.
   - Show a node ghost in the portal while the pointer is outside the canvas, because the real node is clipped
     there.
   - Mark drop targets with `data-drop-zone` and hit-test them with `getBoundingClientRect` on every drag move, for
     the highlight, and again on release.
3. For combining, `getIntersectingNodes` with partial overlap (the default) also fires on about 10 px of edge overlap.
   If that is too eager in practice, use the node under the pointer, or require overlap of at least X % with
   `getOverlappingArea`. It is a UX tuning question, not a blocker.
4. `screenToFlowPosition` is exact (0 px error) at zoom 0.5, 1 and 2, at DPR 1 and 1.5, and with the page scrolled.
   That is the scrolled case of the Jupyter output area, so no extra offset math is needed.
