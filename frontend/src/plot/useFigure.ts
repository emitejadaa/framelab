import { useCallback, useEffect, useRef, useState } from "react";
import { useRpc } from "../data/rpcContext";
import type { FigureSpec, FigureState } from "./types";

const message = (err: unknown) => (err instanceof Error ? err.message : String(err));

/**
 * The figure document, kept in sync with Python: edits show immediately and are sent in order
 * (latest wins); Python validates and normalizes them and owns the undo history.
 */
export function useFigure(id: string) {
  const rpc = useRpc();
  const [server, setServer] = useState<FigureState | null>(null);
  const [spec, setSpec] = useState<FigureSpec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef(false);
  const queued = useRef<FigureSpec | null>(null);
  const current = useRef<FigureSpec | null>(null);

  const show = useCallback((next: FigureSpec) => {
    current.current = next;
    setSpec(next);
  }, []);

  const accept = useCallback(
    (state: FigureState) => {
      setServer(state);
      if (!queued.current) show(state.spec);
    },
    [show],
  );

  const send = useCallback(
    (next: FigureSpec) => {
      if (inflight.current) {
        queued.current = next;
        return;
      }
      inflight.current = true;
      rpc
        .request<FigureState>("figure.update", { id, spec: next as unknown as Record<string, unknown> })
        .then(({ result }) => {
          setError(null);
          accept(result);
        })
        .catch((err) => setError(message(err)))
        .finally(() => {
          inflight.current = false;
          const again = queued.current;
          queued.current = null;
          if (again) send(again);
        });
    },
    [rpc, id, accept],
  );

  const reload = useCallback(() => {
    rpc
      .request<FigureState>("figure.get", { id })
      .then(({ result }) => accept(result))
      .catch((err) => setError(message(err)));
  }, [rpc, id, accept]);

  useEffect(() => {
    reload();
    // Other changes (a deleted source drops layers) arrive as events.
    return rpc.onEvent("figure.changed", (params) => {
      if (params.id === id && !inflight.current && !queued.current) reload();
    });
  }, [rpc, id, reload]);

  const edit = useCallback(
    (change: (draft: FigureSpec) => void) => {
      if (!current.current) return;
      const draft = structuredClone(current.current);
      change(draft);
      show(draft);
      send(draft);
    },
    [send, show],
  );

  const history = useCallback(
    (method: "figure.undo" | "figure.redo") => {
      if (inflight.current || queued.current) return;
      rpc
        .request<FigureState>(method, { id })
        .then(({ result }) => {
          setError(null);
          accept(result);
        })
        .catch((err) => setError(message(err)));
    },
    [rpc, id, accept],
  );

  return {
    server,
    spec,
    error,
    clearError: () => setError(null),
    edit,
    undo: () => history("figure.undo"),
    redo: () => history("figure.redo"),
  };
}
