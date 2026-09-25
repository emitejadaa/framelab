import dagre from "@dagrejs/dagre";
import type { NodeInfo } from "../generated/protocol";

export const NODE_W = 236;
export const NODE_H = 58;

/** Left-to-right layered layout of the whole graph. */
export function layoutGraph(nodes: NodeInfo[]): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 26, ranksep: 90, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(n.id, { width: NODE_W, height: NODE_H });
  for (const n of nodes) for (const p of n.parents) g.setEdge(p, n.id);
  dagre.layout(g);
  const out: Record<string, { x: number; y: number }> = {};
  for (const n of nodes) {
    const p = g.node(n.id);
    out[n.id] = { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 };
  }
  return out;
}
