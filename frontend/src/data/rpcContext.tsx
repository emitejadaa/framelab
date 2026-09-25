import { createContext, useContext } from "react";
import type { Rpc } from "../transport/rpc";

const RpcContext = createContext<Rpc | null>(null);

export const RpcProvider = RpcContext.Provider;

export function useRpc(): Rpc {
  const rpc = useContext(RpcContext);
  if (!rpc) throw new Error("useRpc must be used inside <RpcProvider>");
  return rpc;
}
