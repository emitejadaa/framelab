# S5 — matplotlib preview render budget (matplotlib 3.11.2, Python 3.14.7)

Machine caveat: i5-1235U with the CPU capped at 1.3 GHz, turbo off (shared by other spikes); a normal
laptop is ~2–3× faster. All numbers use `matplotlib.figure.Figure` + `FigureCanvasAgg`, 8×5 in @100 dpi.
Raw data: out/main.json, sweep.json, style.json, export.json, prep.json, griddedup.json, fidelity.json.

## Floor
Empty figure: draw ≈ 80 ms; with `layout="constrained"` ≈ 190–210 ms (layout is the biggest fixed cost).
PNG encode (Pillow, compress_level=1): ≈ 17–25 ms at dpr 1, ≈ 64–95 ms at dpr 2. A tiny custom encoder
(PNG filter 0 + zlib level 1 straight from `buffer_rgba()`) takes ≈ 8–10 ms / 33–41 ms, same sizes.

## Per kind (total = prep + build + draw + encode, dpr 1 / dpr 2)
| kind | 1M raw | 1M reduced | 5M reduced |
|---|---|---|---|
| line | 274 / 402 ms | **M4: 126 / 214 ms** (pixel-identical output, verified) | M4: 214 / 298 ms |
| scatter (uniform) | 2.3 s / 4.8 s | dedup-per-pixel: 234 / 900 ms | random sample 20k: **141 / 258 ms** |
| scatter `c=` colormapped | **27.8 s / 37.9 s** | colour-quantised + sample 20k (5M): 314 / 492 ms | — |
| hist (full data) | 201 / 255 ms | — | — |
| hexbin (full data) | 359 / 484 ms | — | — |
| boxplot (full data) | 130 / 197 ms | — | — |
PNG sizes ≤ 480 KB everywhere (max: colour-mapped scatter at dpr 2).

## Other checks
- `plt.figure(fig)` adopts a `Figure()` built without pyplot; savefig png/svg/pdf work after adoption → `res.figures` can return plain Figures.
- In a kernel, a bare Figure only displays as image/png once the inline backend is configured.
- `ax.boxplot()` and `dict(rcParams)` import pyplot internally (use `rcParams.copy()`; boxplot's import is harmless because framelab figures are not pyplot-managed).
- Export at full data: SVG of a 1M-point line ≈ 134 ms / 269 KB (simplified path); scatter/colour-mapped vector exports need `rasterized=True`.

## Verdict / decisions
- ≤150 ms preview at dpr 1 is met on this throttled CPU for line (M4), scatter (≤20k sample), boxplot; hist/hexbin/constrained layout sit at 200–360 ms here (≈100–150 ms at normal clocks). dpr 2 roughly doubles encode → cap preview rendering at dpr 2 and use the fast encoder.
- **Default preview reduction:** line/step/fill_between → M4 per pixel column (exact); scatter → deterministic random sample of **20 000** points (dedup-per-pixel as an option); colour-mapped scatter → sample 20 000 + colour quantisation; hist/hexbin/boxplot/bar of aggregates → full data.
- **Encoder:** ship the filter-0 + zlib-1 PNG encoder (≈2.5× faster than Pillow at the same size).
- Never render colour-mapped scatter on raw data in the preview (28–38 s at 1M).
- Vector export above ~50k points per artist: warn and offer `rasterized=True`.
