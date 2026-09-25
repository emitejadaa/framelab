import {
  applyNodeChanges,
  Background,
  Controls,
  type Edge,
  MiniMap,
  type Node,
  type NodeChange,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import { type MouseEvent as ReactMouseEvent, type RefObject, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import type { NodeInfo } from "../generated/protocol";
import { useAppStore } from "../state/context";
import { type FigureCardData, FigureCard } from "./FigureCard";
import { isTabular } from "./format";
import { layoutGraph, NODE_H, NODE_W } from "./layout";
import { type CardData, NodeCard } from "./NodeCard";
import { isPlottable, plotNode } from "./plotting";

const nodeTypes = { card: NodeCard, figure: FigureCard };
type Box = "table" | "plot";
type AnyNode = Node<CardData> | Node<FigureCardData>;

const isNodeCard = (n: Node): n is Node<CardData> => n.type === "card";

function inside(box: RefObject<HTMLDivElement | null>, e: ReactMouseEvent | MouseEvent | TouchEvent) {
  const rect = box.current?.getBoundingClientRect();
  if (!rect || !("clientX" in e)) return false;
  return e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;
}

function typing(target: EventTarget | null) {
  return target instanceof HTMLElement && target.closest("input, textarea, select, [contenteditable]") !== null;
}

function CanvasInner() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const snapshot = useAppStore((s) => s.snapshot);
  const selectedId = useAppStore((s) => s.selectedId);
  const select = useAppStore((s) => s.select);
  const openTable = useAppStore((s) => s.openTable);
  const openPlot = useAppStore((s) => s.openPlot);
  const openMenu = useAppStore((s) => s.openMenu);
  const closeMenu = useAppStore((s) => s.closeMenu);
  const askDelete = useAppStore((s) => s.askDelete);
  const askRename = useAppStore((s) => s.askRename);
  const history = useAppStore((s) => s.snapshot?.history);
  const moved = useRef<Record<string, { x: number; y: number }>>({});
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const tableBox = useRef<HTMLDivElement>(null);
  const plotBox = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState<Box | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [nodes, setNodes] = useState<AnyNode[]>([]);
  const container = useRef<HTMLDivElement>(null);
  const flow = useReactFlow();
  const touched = useRef<string | null>(null); // the node the user just clicked or dragged
  const infos = snapshot?.nodes ?? [];
  const figures = snapshot?.figures ?? [];

  useEffect(() => {
    const auto = layoutGraph(infos);
    const cards: AnyNode[] = infos.map((info) => ({
      id: info.id,
      type: "card",
      position: moved.current[info.id] ?? auto[info.id],
      data: { info },
      selected: info.id === selectedId,
    }));
    // Figures sit to the right of their right-most source.
    const stacked: Record<string, number> = {};
    for (const figure of figures) {
      const key = `fig:${figure.id}`;
      const sources = figure.sources.map((s) => moved.current[s] ?? auto[s]).filter(Boolean);
      const anchor = sources.reduce((a, b) => (b.x > a.x ? b : a), sources[0] ?? { x: 20, y: 20 });
      const slot = `${anchor.x},${anchor.y}`;
      stacked[slot] = (stacked[slot] ?? 0) + 1;
      cards.push({
        id: key,
        type: "figure",
        position: moved.current[key] ?? { x: anchor.x + NODE_W + 70, y: anchor.y + (stacked[slot] - 1) * (NODE_H + 16) + 40 },
        data: { figure },
      });
    }
    setNodes(cards);
  }, [infos, figures, selectedId]);

  // Keep the selected node in sight: new nodes appear far right as the graph grows, and the
  // minimap covers the bottom-right corner.
  useEffect(() => {
    if (!selectedId || touched.current === selectedId) return; // never move what is under the pointer
    const node = nodes.find((n) => n.id === selectedId);
    const box = container.current?.getBoundingClientRect();
    if (!node || !box) return;
    const { x, y, zoom } = flow.getViewport();
    const left = node.position.x * zoom + x;
    const top = node.position.y * zoom + y;
    const right = left + NODE_W * zoom;
    const bottom = top + NODE_H * zoom;
    const margin = 24;
    const underMinimap = right > box.width - 230 && bottom > box.height - 180;
    const outside = left < margin || top < 60 || right > box.width - margin || bottom > box.height - margin;
    if (outside || underMinimap) {
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      void flow.setCenter(node.position.x + NODE_W / 2, node.position.y + NODE_H / 2, {
        zoom,
        duration: reduce ? 0 : 200,
      });
    }
    // only when the selection changes or its node first gets a position
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, nodes.some((n) => n.id === selectedId)]);

  const edges: Edge[] = useMemo(
    () => [
      ...infos.flatMap((info) =>
        info.parents.map((p, i) => ({
          id: `${p}->${info.id}`,
          source: p,
          target: info.id,
          label: i === 0 ? info.label : undefined,
          className: "fl-edge",
          labelClassName: "fl-edge-label",
        })),
      ),
      ...figures.flatMap((f) =>
        f.sources.map((s) => ({ id: `${s}->fig:${f.id}`, source: s, target: `fig:${f.id}`, className: "fl-edge-figure" })),
      ),
    ],
    [infos, figures],
  );

  const onNodesChange = useCallback((changes: NodeChange<AnyNode>[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const info = (id: string): NodeInfo | undefined => infos.find((n) => n.id === id);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typing(e.target)) return;
      const key = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && (key === "z" || key === "y")) {
        e.preventDefault();
        const redo = key === "y" || e.shiftKey;
        void rpc.request(redo ? "graph.redo" : "graph.undo").catch(() => undefined);
        return;
      }
      const node = selectedId ? info(selectedId) : undefined;
      if (!node || node.parents.length === 0) return;
      if (e.key === "Delete" || e.key === "Backspace") askDelete(node.id);
      else if (e.key === "F2") {
        e.preventDefault();
        askRename(node.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const plot = async (id: string) => {
    try {
      openPlot(await plotNode(rpc, id));
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    }
  };

  const snapBack = (id: string) => {
    const back = dragStart.current;
    if (back) setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, position: back } : n)));
  };

  return (
    <div className="fl-canvas" ref={container}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={(_e, node) => {
          touched.current = node.id;
          if (isNodeCard(node)) select(node.id);
          closeMenu();
        }}
        onNodeDoubleClick={(_e, node) => {
          if (!isNodeCard(node)) openPlot((node.data as FigureCardData).figure.id);
          else if (isTabular(node.data.info.kind)) openTable(node.id);
        }}
        onNodeContextMenu={(e, node) => {
          e.preventDefault();
          touched.current = node.id;
          if (isNodeCard(node)) openMenu({ nodeId: node.id, x: e.clientX, y: e.clientY });
        }}
        onPaneClick={() => closeMenu()}
        onPaneContextMenu={(e) => e.preventDefault()}
        onNodeDragStart={(_e, node) => {
          touched.current = node.id;
          dragStart.current = node.position;
        }}
        onNodeDrag={(e, node) => {
          if (!isNodeCard(node)) return;
          setOver(inside(tableBox, e) ? "table" : inside(plotBox, e) ? "plot" : null);
        }}
        onNodeDragStop={(e, node) => {
          setOver(null);
          if (!isNodeCard(node)) {
            moved.current[node.id] = node.position;
            return;
          }
          const kind = node.data.info.kind;
          if (inside(tableBox, e) && isTabular(kind)) {
            snapBack(node.id);
            openTable(node.id);
          } else if (inside(plotBox, e) && isPlottable(kind)) {
            snapBack(node.id);
            void plot(node.id);
          } else {
            moved.current[node.id] = node.position;
          }
        }}
        fitView
        fitViewOptions={{ padding: 0.3, maxZoom: 1.2 }}
        minZoom={0.2}
        proOptions={{ hideAttribution: false }}
        nodesConnectable={false}
        deleteKeyCode={null}
      >
        <Background gap={20} size={1} />
        <MiniMap pannable zoomable className="fl-minimap" />
        <Controls showInteractive={false} />
      </ReactFlow>
      <div className="fl-canvas-tools">
        <button
          type="button"
          className="fl-btn"
          disabled={!history?.can_undo}
          title={`${t("workbench.undo")} (Ctrl+Z)`}
          data-testid="undo"
          onClick={() => void rpc.request("graph.undo")}
        >
          ↶
        </button>
        <button
          type="button"
          className="fl-btn"
          disabled={!history?.can_redo}
          title={`${t("workbench.redo")} (Ctrl+Y)`}
          onClick={() => void rpc.request("graph.redo")}
        >
          ↷
        </button>
        {infos.some((n) => ["error", "blocked", "cancelled"].includes(n.state)) ? (
          <button type="button" className="fl-btn fl-btn-quiet-danger" onClick={() => void rpc.request("graph.clear_failed")}>
            {t("workbench.clear_failed")}
          </button>
        ) : null}
      </div>
      <div className="fl-dropzones">
        <div ref={tableBox} className="fl-dropzone" data-over={over === "table" ? "true" : "false"} data-testid="drop-table">
          ▦ {t("workbench.drop_table")}
        </div>
        <div ref={plotBox} className="fl-dropzone" data-over={over === "plot" ? "true" : "false"} data-testid="drop-plot">
          ▟ {t("workbench.drop_plot")}
        </div>
      </div>
      {problem ? (
        <button type="button" className="fl-canvas-error" onClick={() => setProblem(null)}>
          {problem} ×
        </button>
      ) : null}
      {infos.length <= 3 ? <div className="fl-canvas-hint">{t("workbench.hint")}</div> : null}
    </div>
  );
}

export function Canvas() {
  return (
    <ReactFlowProvider>
      <CanvasInner />
    </ReactFlowProvider>
  );
}
