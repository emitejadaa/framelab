import { useEffect, useState } from "react";
import { RpcError } from "../transport/rpc";
import { useRpc } from "./rpcContext";
import { type DecodedWindow, decodeWindow, type WindowMeta } from "./window";

export interface ColumnInfo {
  text: string;
  label: unknown;
  literal: string | null;
  dtype: string;
  nulls: number;
}

export interface Summary {
  id: string;
  name: string;
  kind: string;
  shape?: number[];
  memory_bytes?: number;
  columns?: ColumnInfo[];
  ngroups?: number;
  keys?: string[];
  grouped?: string;
  type?: string;
  repr?: string;
  dtype?: string;
}

interface Loadable<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

function message(err: unknown): string {
  return err instanceof RpcError || err instanceof Error ? err.message : String(err);
}

/** node.summary for a node, refetched when `version` (e.g. its state) changes. */
export function useSummary(id: string | null, version: string): Loadable<Summary> {
  const rpc = useRpc();
  const [state, setState] = useState<Loadable<Summary>>({ data: null, error: null, loading: false });
  useEffect(() => {
    if (!id || version !== "ready") {
      setState({ data: null, error: null, loading: version === "pending" || version === "computing" });
      return;
    }
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    rpc
      .request<Summary>("node.summary", { id })
      .then(({ result }) => alive && setState({ data: result, error: null, loading: false }))
      .catch((err) => alive && setState({ data: null, error: message(err), loading: false }));
    return () => {
      alive = false;
    };
  }, [id, version, rpc]);
  return state;
}

/** A decoded Arrow row window for a node. */
export function useWindow(
  id: string | null,
  version: string,
  offset: number,
  limit: number,
): Loadable<DecodedWindow> {
  const rpc = useRpc();
  const [state, setState] = useState<Loadable<DecodedWindow>>({ data: null, error: null, loading: false });
  useEffect(() => {
    if (!id || version !== "ready") {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    rpc
      .request<WindowMeta>("node.window", { id, offset, limit })
      .then(({ result, buffers }) => {
        if (alive) setState({ data: decodeWindow(result, buffers[0]), error: null, loading: false });
      })
      .catch((err) => alive && setState({ data: null, error: message(err), loading: false }));
    return () => {
      alive = false;
    };
  }, [id, version, offset, limit, rpc]);
  return state;
}
