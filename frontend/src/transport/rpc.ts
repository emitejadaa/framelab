import { type Envelope, PROTOCOL_VERSION } from "../generated/protocol";
import type { Transport } from "./types";

export class RpcError extends Error {
  constructor(
    readonly code: string,
    readonly i18nKey: string,
    message: string,
    readonly traceback?: string,
  ) {
    super(message);
  }
}

type EventCallback = (params: Record<string, unknown>, buffers: DataView[], env: Envelope) => void;

export interface Rpc {
  request<T = unknown>(
    method: string,
    params?: Record<string, unknown>,
    buffers?: ArrayBuffer[],
  ): Promise<{ result: T; buffers: DataView[] }>;
  onEvent(method: string, cb: EventCallback): () => void;
  dispose(): void;
}

interface Pending {
  resolve: (value: { result: unknown; buffers: DataView[] }) => void;
  reject: (reason: RpcError) => void;
  timer: ReturnType<typeof setTimeout>;
}

export function createRpc(transport: Transport, timeoutMs = 30_000): Rpc {
  let seq = 0;
  const pending = new Map<string, Pending>();
  const events = new Map<string, Set<EventCallback>>();

  const off = transport.onMessage((env, buffers) => {
    if (env.type === "res" && env.id !== undefined) {
      const entry = pending.get(env.id);
      if (!entry) return;
      pending.delete(env.id);
      clearTimeout(entry.timer);
      if (env.error) {
        const e = env.error;
        entry.reject(new RpcError(e.code, e.i18n_key, e.message, e.traceback));
      } else {
        entry.resolve({ result: env.result, buffers });
      }
    } else if (env.type === "evt" && env.method) {
      for (const key of [env.method, "*"]) {
        for (const cb of events.get(key) ?? []) cb(env.params ?? {}, buffers, env);
      }
    }
  });

  return {
    request<T>(method: string, params: Record<string, unknown> = {}, buffers: ArrayBuffer[] = []) {
      const id = `c${++seq}`;
      return new Promise<{ result: T; buffers: DataView[] }>((resolve, reject) => {
        const timer = setTimeout(() => {
          pending.delete(id);
          reject(new RpcError("timeout", "errors.timeout", `${method} timed out`));
        }, timeoutMs);
        pending.set(id, { resolve: resolve as Pending["resolve"], reject, timer });
        transport.send({ v: PROTOCOL_VERSION, id, type: "req", method, params }, buffers);
      });
    },
    onEvent(method, cb) {
      const set = events.get(method) ?? new Set<EventCallback>();
      set.add(cb);
      events.set(method, set);
      return () => {
        set.delete(cb);
      };
    },
    dispose() {
      off();
      for (const entry of pending.values()) {
        clearTimeout(entry.timer);
        entry.reject(new RpcError("closed", "errors.closed", "connection closed"));
      }
      pending.clear();
      events.clear();
    },
  };
}
