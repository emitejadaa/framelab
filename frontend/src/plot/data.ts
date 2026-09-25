import { useEffect, useState } from "react";
import { useRpc } from "../data/rpcContext";
import type { Catalog, LayerSpec, SourceFields } from "./types";

/** plot.catalog: chart kinds, styles, colormaps… (fetched once per Plotter tab). */
export function useCatalog(): Catalog | null {
  const rpc = useRpc();
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  useEffect(() => {
    let alive = true;
    rpc.request<Catalog>("plot.catalog").then(({ result }) => alive && setCatalog(result));
    return () => {
      alive = false;
    };
  }, [rpc]);
  return catalog;
}

/** The fields (index, columns, values) a node offers, refetched when it becomes ready. */
export function useFields(nodeId: string | null, state: string): SourceFields | null {
  const rpc = useRpc();
  const [fields, setFields] = useState<SourceFields | null>(null);
  useEffect(() => {
    setFields(null);
    if (!nodeId || state !== "ready") return;
    let alive = true;
    rpc
      .request<SourceFields>("plot.fields", { id: nodeId })
      .then(({ result }) => alive && setFields(result))
      .catch(() => alive && setFields(null));
    return () => {
      alive = false;
    };
  }, [rpc, nodeId, state]);
  return fields;
}

export function useSuggestions(nodeId: string | null, state: string): Partial<LayerSpec>[] {
  const rpc = useRpc();
  const [layers, setLayers] = useState<Partial<LayerSpec>[]>([]);
  useEffect(() => {
    setLayers([]);
    if (!nodeId || state !== "ready") return;
    let alive = true;
    rpc
      .request<{ layers: Partial<LayerSpec>[] }>("plot.suggest", { id: nodeId })
      .then(({ result }) => alive && setLayers(result.layers))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [rpc, nodeId, state]);
  return layers;
}

/** A complete layer from Python's first guess for this kind and data. */
export function blankLayer(partial: Partial<LayerSpec>): LayerSpec {
  return {
    kind: partial.kind ?? "line",
    source: partial.source ?? "",
    x: partial.x ?? null,
    y: partial.y ?? [],
    hue: partial.hue ?? null,
    color_by: partial.color_by ?? null,
    size_by: partial.size_by ?? null,
    rows: partial.rows ?? { mode: "all" },
    props: partial.props ?? {},
    label: partial.label ?? "",
  };
}

/** Copy a received buffer into a standalone byte array (Blob needs a plain ArrayBuffer). */
export function bytesOf(view: DataView): Uint8Array<ArrayBuffer> {
  return new Uint8Array(view.buffer, view.byteOffset, view.byteLength).slice();
}
