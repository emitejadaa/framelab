import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { NodeInfo } from "../generated/protocol";
import { useAppStore } from "../state/context";
import { isPlottable } from "../workbench/plotting";
import { blankLayer, useCatalog } from "./data";
import { ExportDialog } from "./ExportDialog";
import { Gallery } from "./Gallery";
import { KindIcon } from "./icons";
import { AxesPanel, FigurePanel, LayerPanel } from "./Panels";
import { FigureCode, Preview } from "./Preview";
import type { FigureSpec, LayerSpec, RenderMeta, Selection } from "./types";
import { useFigure } from "./useFigure";

function typing(target: EventTarget | null) {
  return target instanceof HTMLElement && target.closest("input, textarea, select, [contenteditable]") !== null;
}

function Structure({
  spec,
  selection,
  select,
  nodes,
  errors,
  edit,
}: {
  spec: FigureSpec;
  selection: Selection;
  select(s: Selection): void;
  nodes: NodeInfo[];
  errors: Map<string, string>;
  edit(change: (d: FigureSpec) => void): void;
}) {
  const { t } = useTranslation();
  const grid = spec.nrows * spec.ncols > 1;
  const is = (s: Selection) => JSON.stringify(s) === JSON.stringify(selection);
  const move = (k: number, j: number, by: number) =>
    edit((d) => {
      const layers = d.axes[k].layers;
      const [layer] = layers.splice(j, 1);
      layers.splice(j + by, 0, layer);
      select({ type: "layer", axes: k, layer: j + by });
    });
  return (
    <div className="fl-structure" data-testid="structure">
      <button
        type="button"
        className="fl-tree-item fl-tree-figure"
        data-active={is({ type: "figure" }) ? "true" : "false"}
        onClick={() => select({ type: "figure" })}
      >
        ▟ <span className="fl-mono">{spec.name}</span>
      </button>
      {spec.axes.map((axes, k) => (
        <div key={k} className="fl-tree-axes">
          <button
            type="button"
            className="fl-tree-item"
            data-active={is({ type: "axes", axes: k }) ? "true" : "false"}
            onClick={() => select({ type: "axes", axes: k })}
          >
            ▭ {t("plot.axes_n", { n: k + 1 })}
            {grid ? <span className="fl-muted"> · {t("plot.cell", { row: Math.floor(k / spec.ncols) + 1, col: (k % spec.ncols) + 1 })}</span> : null}
            {axes.title ? <span className="fl-muted"> · {axes.title}</span> : null}
          </button>
          {axes.layers.map((layer, j) => {
            const error = errors.get(`${k}:${j}`);
            const source = nodes.find((n) => n.id === layer.source)?.name ?? "?";
            return (
              <div key={j} className="fl-tree-layer" data-error={error ? "true" : "false"} title={error}>
                <button
                  type="button"
                  className="fl-tree-item"
                  data-active={is({ type: "layer", axes: k, layer: j }) ? "true" : "false"}
                  data-testid={`layer-${k}-${j}`}
                  onClick={() => select({ type: "layer", axes: k, layer: j })}
                >
                  <KindIcon kind={layer.kind} />
                  <span>
                    {t(`plot.kind.${layer.kind}`)} <span className="fl-muted">· {source}</span>
                  </span>
                </button>
                <span className="fl-tree-tools">
                  <button type="button" disabled={j === 0} title={t("plot.move_up")} onClick={() => move(k, j, -1)}>
                    ↑
                  </button>
                  <button type="button" disabled={j === axes.layers.length - 1} title={t("plot.move_down")} onClick={() => move(k, j, 1)}>
                    ↓
                  </button>
                </span>
              </div>
            );
          })}
          <button
            type="button"
            className="fl-tree-add"
            data-active={is({ type: "gallery", axes: k }) ? "true" : "false"}
            data-testid={`add-layer-${k}`}
            onClick={() => select({ type: "gallery", axes: k })}
          >
            + {t("plot.add_layer")}
          </button>
        </div>
      ))}
    </div>
  );
}

export function PlotView({ figureId }: { figureId: string }) {
  const { t } = useTranslation();
  const figure = useFigure(figureId);
  const catalog = useCatalog();
  const showWorkbench = useAppStore((s) => s.showWorkbench);
  const allNodes = useAppStore((s) => s.snapshot?.nodes);
  const nodes = useMemo(() => allNodes ?? [], [allNodes]);
  const sources = useMemo(() => nodes.filter((n) => isPlottable(n.kind)), [nodes]);
  const selectedNode = useAppStore((s) => s.selectedId);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [meta, setMeta] = useState<RenderMeta | null>(null);
  const [exporting, setExporting] = useState(false);
  const [gallerySource, setGallerySource] = useState<string | null>(null);
  const { spec, server, edit } = figure;

  // First view: the gallery for an empty figure, else its first layer.
  useEffect(() => {
    if (!spec || selection) return;
    const hasLayers = spec.axes[0]?.layers.length > 0;
    setSelection(hasLayers ? { type: "layer", axes: 0, layer: 0 } : { type: "gallery", axes: 0 });
  }, [spec, selection]);

  // Keep the selection valid when layers or axes disappear (undo, grid changes, deleted nodes).
  useEffect(() => {
    if (!spec || !selection || selection.type === "figure") return;
    const axes = spec.axes[selection.axes];
    if (!axes) setSelection({ type: "figure" });
    else if (selection.type === "layer" && !axes.layers[selection.layer]) {
      setSelection(axes.layers.length ? { type: "layer", axes: selection.axes, layer: axes.layers.length - 1 } : { type: "axes", axes: selection.axes });
    }
  }, [spec, selection]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || typing(e.target)) return;
      const key = e.key.toLowerCase();
      if (key === "z" && !e.shiftKey) {
        e.preventDefault();
        figure.undo();
      } else if (key === "y" || (key === "z" && e.shiftKey)) {
        e.preventDefault();
        figure.redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const errors = useMemo(() => new Map((meta?.errors ?? []).map((e) => [`${e.axes}:${e.layer}`, e.message])), [meta]);
  const used = useMemo(() => new Set(spec?.axes.flatMap((a) => a.layers.map((l) => l.source)) ?? []), [spec]);
  const inputs = nodes
    .filter((n) => used.has(n.id))
    .map((n) => `${n.id}:${n.state}`)
    .join(",");

  if (!spec || !server || !catalog || !selection) {
    return (
      <div className="fl-plotview fl-muted fl-center-msg">
        {figure.error ?? t("app.loading")}
      </div>
    );
  }

  const defaultSource =
    gallerySource ??
    (selection.type === "gallery" ? spec.axes[selection.axes]?.layers[0]?.source : undefined) ??
    server.origin ??
    (selectedNode && sources.some((n) => n.id === selectedNode) ? selectedNode : null) ??
    sources[0]?.id ??
    null;

  const addLayer = (k: number, partial: Partial<LayerSpec>) => {
    const j = spec.axes[k].layers.length;
    edit((d) => void d.axes[k].layers.push(blankLayer(partial)));
    setSelection({ type: "layer", axes: k, layer: j });
  };

  let panel = null;
  if (selection.type === "figure") {
    panel = <FigurePanel spec={spec} catalog={catalog} edit={edit} />;
  } else if (selection.type === "axes" && spec.axes[selection.axes]) {
    const k = selection.axes;
    panel = <AxesPanel axes={spec.axes[k]} index={k} catalog={catalog} change={(fn) => edit((d) => fn(d.axes[k]))} />;
  } else if (selection.type === "gallery") {
    const k = selection.axes;
    panel = (
      <Gallery
        catalog={catalog}
        sources={sources}
        source={defaultSource}
        onSource={setGallerySource}
        onPick={(layer) => addLayer(k, layer)}
      />
    );
  } else if (selection.type === "layer") {
    const { axes: k, layer: j } = selection;
    const layer = spec.axes[k]?.layers[j];
    if (layer) {
      panel = (
        <LayerPanel
          key={`${k}:${j}`}
          layer={layer}
          catalog={catalog}
          sources={sources}
          error={errors.get(`${k}:${j}`) ?? null}
          change={(fn) => edit((d) => fn(d.axes[k].layers[j]))}
          replace={(l) => edit((d) => void (d.axes[k].layers[j] = l))}
          remove={() => {
            edit((d) => void d.axes[k].layers.splice(j, 1));
            setSelection({ type: "axes", axes: k });
          }}
        />
      );
    }
  }

  return (
    <div className="fl-plotview" data-testid="plot-view">
      <div className="fl-toolbar">
        <button type="button" className="fl-btn" onClick={showWorkbench}>
          ← {t("tabs.workbench")}
        </button>
        <span className="fl-toolbar-title">▟ {spec.name}</span>
        <button type="button" className="fl-btn" disabled={!server.can_undo} title={`${t("plot.undo")} (Ctrl+Z)`} onClick={figure.undo}>
          ↶
        </button>
        <button type="button" className="fl-btn" disabled={!server.can_redo} title={`${t("plot.redo")} (Ctrl+Y)`} onClick={figure.redo}>
          ↷
        </button>
        {figure.error ? (
          <button type="button" className="fl-toolbar-error" onClick={figure.clearError} title={t("plot.dismiss")}>
            {figure.error} ×
          </button>
        ) : null}
        <span className="fl-spacer" />
        <button type="button" className="fl-btn fl-btn-primary" data-testid="export" onClick={() => setExporting(true)}>
          {t("plot.export.button")}
        </button>
      </div>
      <div className="fl-plot-body">
        <aside className="fl-plot-left">
          <Structure spec={spec} selection={selection} select={setSelection} nodes={nodes} errors={errors} edit={edit} />
        </aside>
        <main className="fl-plot-center">
          <Preview figureId={figureId} version={server.version} inputs={inputs} onMeta={setMeta} />
          <FigureCode figureId={figureId} version={`${server.version}:${server.exported?.path ?? ""}:${inputs}`} />
        </main>
        <aside className="fl-plot-right">{panel}</aside>
      </div>
      {exporting ? <ExportDialog figureId={figureId} spec={spec} catalog={catalog} onClose={() => setExporting(false)} /> : null}
    </div>
  );
}
