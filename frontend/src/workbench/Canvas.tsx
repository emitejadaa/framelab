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
} from "@xyflow/react";
import { type MouseEvent as ReactMouseEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../state/context";
import { isTabular } from "./format";
import { layoutGraph } from "./layout";
import { type CardData, NodeCard } from "./NodeCard";

const nodeTypes = { card: NodeCard };

function CanvasInner() {
  const { t } = useTranslation();
  const snapshot = useAppStore((s) => s.snapshot);
  const selectedId = useAppStore((s) => s.selectedId);
  const select = useAppStore((s) => s.select);
  const openTable = useAppStore((s) => s.openTable);
  const openMenu = useAppStore((s) => s.openMenu);
  const closeMenu = useAppStore((s) => s.closeMenu);
  const moved = useRef<Record<string, { x: number; y: number }>>({});
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const tableBox = useRef<HTMLDivElement>(null);
  const [overBox, setOverBox] = useState(false);
  const [nodes, setNodes] = useState<Node<CardData>[]>([]);
  const infos = snapshot?.nodes ?? [];

  useEffect(() => {
    const auto = layoutGraph(infos);
    setNodes(
      infos.map((info) => ({
        id: info.id,
        type: "card",
        position: moved.current[info.id] ?? auto[info.id],
        data: { info },
        selected: info.id === selectedId,
      })),
    );
  }, [infos, selectedId]);

  const edges: Edge[] = useMemo(
    () =>
      infos.flatMap((info) =>
        info.parents.map((p, i) => ({
          id: `${p}->${info.id}`,
          source: p,
          target: info.id,
          label: i === 0 ? info.label : undefined,
          className: "fl-edge",
          labelClassName: "fl-edge-label",
        })),
      ),
    [infos],
  );

  const onNodesChange = useCallback((changes: NodeChange<Node<CardData>>[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  }, []);

  const inBox = (e: ReactMouseEvent | MouseEvent | TouchEvent) => {
    const rect = tableBox.current?.getBoundingClientRect();
    if (!rect || !("clientX" in e)) return false;
    return e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom;
  };

  return (
    <div className="fl-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={(_e, node) => {
          select(node.id);
          closeMenu();
        }}
        onNodeDoubleClick={(_e, node) => {
          if (isTabular((node.data as CardData).info.kind)) openTable(node.id);
        }}
        onNodeContextMenu={(e, node) => {
          e.preventDefault();
          openMenu({ nodeId: node.id, x: e.clientX, y: e.clientY });
        }}
        onPaneClick={() => closeMenu()}
        onPaneContextMenu={(e) => e.preventDefault()}
        onNodeDragStart={(_e, node) => {
          dragStart.current = node.position;
        }}
        onNodeDrag={(e) => setOverBox(inBox(e))}
        onNodeDragStop={(e, node) => {
          setOverBox(false);
          if (inBox(e) && isTabular((node.data as CardData).info.kind)) {
            const back = dragStart.current;
            if (back) setNodes((ns) => ns.map((n) => (n.id === node.id ? { ...n, position: back } : n)));
            openTable(node.id);
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
      <div className="fl-dropzones">
        <div ref={tableBox} className="fl-dropzone" data-over={overBox ? "true" : "false"}>
          ▦ {t("workbench.drop_table")}
        </div>
        <div className="fl-dropzone" data-disabled="true" title={t("workbench.plot_soon")}>
          ▟ {t("workbench.drop_plot")}
        </div>
      </div>
      <div className="fl-canvas-hint">{t("workbench.hint")}</div>
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
