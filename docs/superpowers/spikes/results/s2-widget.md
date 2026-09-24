# S2: the framelab widget in JupyterLab (rendering, CSS isolation, keys, context menu)

**Verdict: PARTIAL PASS.** Rendering, timing, outbound CSS isolation, two independent widgets and the context menu all pass. The notebook shortcuts check (e) **fails** with the current bundle: clicking the widget and pressing `a`/`b` inserts notebook cells. The fix is one attribute, and I checked it live. A second problem showed up that the brief did not ask about. JupyterLab's own CSS leaks **into** the widget, because framelab's styles sit in `@layer` blocks. It does not affect the current Shell yet, but it has to be fixed before real UI lands.

## Setup

- Machine: Arch Linux x86_64 (kernel 7.2.3), Intel i5-1235U (12 threads), about 7.6 GB RAM.
- Software: Python 3.14.7, pandas 3.0.6, JupyterLab 4.6.4 (jupyter_server 2.21.1), anywidget 0.11.0, ipywidgets 8.1.9.
- Browser: Chromium 152.0.7977.82, headless, driven by playwright-core 1.63.0 (`executablePath: /usr/bin/chromium`, no browser download). Viewport 1400×1000, locale en-US.
- Bundle under test: `src/framelab/_static/framelab.js`, sha256 prefix `8e6186d1ab99a58e`, built 2026-09-23 22:47.

## Commands

```bash
.venv/bin/python spikes/s2-widget/make_notebooks.py          # check.ipynb + control.ipynb (nbformat)
.venv/bin/jupyter lab --no-browser --port 8899 --IdentityProvider.token=s2spike \
    --ServerApp.root_dir=spikes/s2-widget \
    --LabApp.workspaces_dir=spikes/s2-widget/.lab-workspaces \
    --LabApp.user_settings_dir=spikes/s2-widget/.lab-settings   # background; autosave + news disabled there
cd spikes/s2-widget/js && mise exec -- pnpm add playwright-core    # PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
COLD_RUNS=5 WARM_RUNS=3 mise exec -- node run_spike.mjs          # -> results.json, lab.png, widget-ventas.png
mise exec -- node shadow_experiment.mjs                          # -> shadow_results.json (tests a candidate fix)
.venv/bin/python spikes/s2-widget/kernel_timing.py               # explore() cost inside the kernel (nbclient), x3
curl -X POST -H 'Authorization: token s2spike' localhost:8899/api/shutdown   # JupyterLab stopped
```

How `run_spike.mjs` works:

- **Cold runs:** it deletes every kernel session through the REST API, then opens `/lab/tree/check.ipynb?reset`. It waits until the status bar has shown `Python 3 (ipykernel) | Idle` for 500 ms, then runs **Run → Run All Cells**.
- **Timing:** t0 is the `pointerup` on the menu item. A `MutationObserver` records `performance.now()` at four events:
  - each prompt reaches `[*]`
  - each prompt reaches `[n]`
  - each `.fl-root` appears
  - each `[data-testid=root-item]` shows its text
- **Warm runs:** Run All again on the same kernel.

## (a) Time to render: PASS

The brief sets no budget, so these are recorded numbers. Times are ms from clicking Run All to the text appearing in the widget.

| | `ventas · 1000 × 5` | `clientes · 250 × 2` |
|---|---|---|
| Cold kernel, 5 runs (min / median / max) | 1185 / **1696** / 1953 | 1305 / **1850** / 2106 |
| Warm kernel, 3 runs | 541 / **623** / 697 | 630 / **709** / 815 |
| Re-run of the `clientes` cell only | n/a | **436** |

Where the time goes:

- **Cold runs are mostly kernel time.** Cell 1 takes 893–1538 ms to finish. Inside the kernel, measured with nbclient over 3 runs:
  - `import pandas`: 705–966 ms
  - `import framelab`: 14–24 ms (anywidget is imported lazily)
  - first `fl.explore()`: 164–290 ms
  - later `explore()` calls: 16–22 ms median
  - `FramelabWidget(...)` constructor: 13–20 ms median
- **Widget side:** the loader (`.fl-root`) appears 89–164 ms after cell 1 finishes. The text appears 120–216 ms after the **last** cell finishes.
- **The handshake waits for the whole Run All.** Widget 1 never shows its text before cell 2 has finished, in all 8 runs. The widget's `session.hello` and `session.snapshot` calls go to the kernel as comm messages, which queue behind any running cell. So a busy kernel freezes the widget. This confirms the spec's "kernel busy" warning is needed.
- **Payload size:** each widget's `comm_open` is **423,584 B** on the kernel websocket, because the whole ESM travels in the model state. Run All with two widgets receives 1.14 MB over the websocket. That total includes two 133 KB `debug_reply` frames from JupyterLab's debugger, which have nothing to do with framelab.

## (b) framelab CSS does not leak into the notebook: PASS

- **What was compared:** the full computed style (1287 properties) of the Markdown `h1` and `p` in `control.ipynb`, against `check.ipynb` with both widgets rendered. Also compared: `body`, `html`, the menu bar label, `.jp-InputPrompt`, `.cm-line` and `.jp-Notebook`, and `check.ipynb` before vs after running.
- **Result:** 0 differences in `font-family`, `font-size`, `font-weight`, `line-height`, `color`, margins, padding, `letter-spacing` and `text-transform` for h1 and p. For example, h1 is `29.0304px`, weight 500, `rgba(0,0,0,0.87)`, margin 17.42/23.22 px in both.
- **Only difference:** 6 inherited custom properties on every element: `--fl-font-sans`, `--fl-font-mono`, `--fl-spacing`, `--fl-text-xs`, `--fl-text-xs--line-height`, `--fl-tracking-wide`. They come from Tailwind's `@layer theme{:root,:host{…}}`. Nothing visible changes, but framelab does write global variables.
  - The `.jp-InputPrompt` colour also differed. That is only because a different cell was active, not a leak.
- anywidget injects **one** `<style>` for both widgets, so the CSS is not duplicated.

## (c) Two widgets render independently: PASS

- There are 2 `.fl-root` elements, in cells 1 and 2. Each is 720 px tall, has its own `.fl-portal` child and shows only its own frame.
- Re-running only the `clientes` cell rebuilt that widget in 436 ms. The `ventas` widget stayed intact.
- There were 0 console errors or warnings in the whole run.

## (d) Right-click does not open JupyterLab's menu: PASS

- **Positive control:** right-clicking the Markdown cell opens 1 `.lm-Menu`.
- Right-clicking the `ventas` item, the `clientes` item or the empty widget background opens **0** `.lm-Menu`. `data-jp-suppress-context-menu` works through `closest()`.
- **Caveat:** the `contextmenu` event arrives with `defaultPrevented=false`, so Chromium's **native** menu opens inside the widget. Any future framelab menu must call `preventDefault()`.

## (e) Notebook shortcuts inside the widget: FAIL as shipped

| Trial | Focus after click | Cells inserted |
|---|---|---|
| Click `ventas` item, press `a`, `b` (as shipped) | `div.jp-Cell` (outside `.fl-root`) | **2** |
| Same for `clientes` | `div.jp-Cell` | **2** |
| Positive control: click Markdown cell, Esc, `b` | `div.jp-Cell` | 1 |
| **With `.fl-root` given `tabindex="-1"` at runtime**, press `a`, `b` (both widgets) | `div.fl-root` | **0** |
| Same, then `Shift+Enter`, `Ctrl+Enter`, `d d`, `m`, `x` | `div.fl-root` | 0 (prompts unchanged, no cell changed type) |
| `<input>` inside `.fl-root`: type `a`, `b`, `Shift+Enter` | `INPUT` | 0 (value `"ab"`) |

**Cause:**

- `.fl-root` in `frontend/src/app/App.tsx` is not focusable. A click inside the widget therefore leaves focus on the notebook cell node.
- Lumino's key-binding walk starts at `event.target`, which is that cell and is outside `.fl-root`. So the walk never reaches `data-lm-suppress-shortcuts`, and command-mode `a`/`b` fire.

**Minimal fix:** add `tabIndex={-1}` to the `.fl-root` div in `App.tsx`. Optionally also add `onPointerDown={(e) => { if (e.target === e.currentTarget || !(e.target as Element).closest("input,textarea,select,button,[tabindex]")) e.currentTarget.focus({ preventScroll: true }); }}` so focus also lands there on the widget background. Everything else in `App.tsx` stays as it is.

I verified the fix at runtime. All shortcut trials insert 0 cells, and Shift/Ctrl+Enter no longer re-run the cell, which would otherwise destroy the widget. Add an outline style for `.fl-root:focus-visible` (or `outline: none`) at the same time.

## (f) Screenshot and bundle size

- `lab.png`: full notebook with both widgets. `widget-ventas.png`: the `ventas` widget alone.
- Bundle sizes:

| File | Raw | gzip -9 | brotli -q11 |
|---|---|---|---|
| `framelab.js` | 370,267 B | 96,446 B | 82,145 B |
| `framelab.css` | 3,137 B | 1,328 B | 1,125 B |

- `framelab.js` is **not whitespace-minified**: 10,932 lines with `//#region` comments. Vite library mode does not minify whitespace for `es` output. Running `esbuild --minify` on it gives 277,537 B (-25 %; gzip 87,808 B). Every widget ships the ESM over the comm, so this directly shrinks the 423 KB per-widget `comm_open`.

## Problem found: JupyterLab CSS leaks into the widget

framelab's reset and utilities are in `@layer base` and `@layer utilities`. JupyterLab's CSS is **unlayered**, and unlayered rules always win over layered ones, whatever the specificity. I injected probe elements into `.fl-root` and listed the matched rules through the Chrome DevTools Protocol:

| Probe inside `.fl-root` | Host rule that wins | Effect |
|---|---|---|
| `<pre class="fl:p-4">` | `.jp-OutputArea-output pre{padding:0;margin:0;white-space:pre-wrap…}` | padding **0px** instead of 16px |
| `pre`, `code`, `kbd` | `.jp-ThemedContainer code…{font-family:var(--jp-code-font-family)}` | Menlo/DejaVu instead of framelab mono |
| `button` | `:where(.jp-ThemedContainer) button{font-family:…}`, `.jp-ThemedContainer button{border-radius}` | JupyterLab UI font, radius 2px |
| `a` | `.jp-ThemedContainer a{color:unset;text-decoration:unset}` | no underline |
| `dl`, `dd` | `.jp-OutputArea-output dd{float:left;width:80%}` | layout broken |

The current Shell (`h2`, `ul`, `li`) matches no host rules, so it renders correctly today.

**Shadow DOM experiment (`shadow_results.json`):**

- **Setup:** the same `framelab.css` goes into a shadow root through `adoptedStyleSheets`. The host `<div>` carries `data-lm-suppress-shortcuts` and `data-jp-suppress-context-menu`, and `.fl-root` gets `tabindex=-1`.
- **CSS:** every probe gets framelab's intended style: pre padding 16px, JetBrains-mono stack on `pre`/`code`/`kbd`, Inter on `button`, no float on `dd`.
- **Globals:** the `:root,:host` theme variables land on the host only.
- **Keys and menu:** `a`/`b` insert 0 cells and typing into an input works (`"ab"`). Right-click opens 0 `.lm-Menu`, because Lumino sees the retargeted host, which carries both attributes.

## Not tested locally

- **VS Code, Colab, JupyterHub:** cannot be tested on this machine. The design only relies on anywidget comms, so revisit in M7.
- **Notebook 7:** the `notebook` package is not installed, so it was not tested.
- **JupyterLab dark theme:** not tested. Note that `.fl-root[data-theme=system]` follows the OS `prefers-color-scheme`, not the JupyterLab theme.

## Decisions for framelab

1. **The notebook path works:** keep anywidget 0.11 inline rendering. The notebook check "`fl.explore(df)` shows `ventas · 1000 × 5` in JupyterLab" passes. Render cost on the widget side is about 90–200 ms plus two RPC round trips. Cold time is dominated by `import pandas`.
2. **Fix (e) before M0 closes:** `tabIndex={-1}` on `.fl-root` (plus focus on pointerdown), with a `:focus-visible` style.
3. **Choose an isolation strategy before M1 UI work** (forms, code view, menus):
   - **Preferred:** render into a **shadow root**. It isolates in both directions, drops the global `--fl-*` vars, and works with both JupyterLab attributes on the host, as shown here. anywidget's `_css` would then be imported into the shadow root instead of `document.head`. Portals already target the in-root `PortalContainer`.
   - **Risk:** Glide, React Flow, Base UI and cmdk must be checked inside a shadow root (focus and outside-click retargeting). Add that to S1/M3.
   - **Fallback:** keep the light DOM, but emit framelab utilities and reset **unlayered with `!important`** (Tailwind `important`), and drop the `@layer` wrappers.
4. **Right-click:** framelab's own menus must `preventDefault()` on `contextmenu`, or the native browser menu opens over them.
5. **Bundle:** minify the ES output. Vite lib mode needs `build.minify` plus a post-minify step, or an app-style build of a single ESM entry: 370 KB goes to about 278 KB. Each widget sends the full ESM in `comm_open` (423 KB per widget). That is acceptable locally, but it grows the notebook if widget state is saved. Keep "save widget state" off, which is the default.

## Files

All in `spikes/s2-widget/`:

- `make_notebooks.py`, `check.ipynb`, `control.ipynb`
- `js/run_spike.mjs`, `js/shadow_experiment.mjs`
- `kernel_timing.py`
- `results.json` (raw numbers), `shadow_results.json`
- `lab.png`, `widget-ventas.png`
- `jupyter.log`
