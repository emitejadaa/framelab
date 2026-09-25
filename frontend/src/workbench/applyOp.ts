import type { NodeInfo } from "../generated/protocol";
import type { OpJson } from "../ops/build";
import type { Rpc } from "../transport/rpc";

/** Ask Python to create a node; resolves with its info (state "pending"). */
export async function applyOp(rpc: Rpc, op: OpJson, opts: { force?: boolean } = {}): Promise<NodeInfo> {
  const params: Record<string, unknown> = { op: op as unknown as Record<string, unknown> };
  if (opts.force) params.force = true;
  const { result } = await rpc.request<{ node: NodeInfo }>("node.apply", params);
  return result.node;
}
