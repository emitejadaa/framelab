import type { Rpc } from "../transport/rpc";

/** Create a figure that draws `nodeId`; resolves with the figure id. */
export async function plotNode(rpc: Rpc, nodeId: string): Promise<string> {
  const { result } = await rpc.request<{ id: string }>("figure.create", { source: nodeId });
  return result.id;
}

export const isPlottable = (kind: string) => kind === "DataFrame" || kind === "Series";
