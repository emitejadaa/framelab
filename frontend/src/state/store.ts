import { createStore } from "zustand/vanilla";
import type { HelloResult, SessionSnapshot } from "../generated/protocol";

export type ConnectionState = "connecting" | "ready" | "mismatch" | "error";

export interface AppState {
  connection: ConnectionState;
  error: string | null;
  hello: HelloResult | null;
  snapshot: SessionSnapshot | null;
  setConnection(connection: ConnectionState, error?: string | null): void;
  setHello(hello: HelloResult): void;
  setSnapshot(snapshot: SessionSnapshot): void;
}

export type AppStore = ReturnType<typeof createAppStore>;

/** One store per mounted UI (never a module singleton: two widgets can share a page). */
export function createAppStore() {
  return createStore<AppState>()((set) => ({
    connection: "connecting",
    error: null,
    hello: null,
    snapshot: null,
    setConnection: (connection, error = null) => set({ connection, error }),
    setHello: (hello) => set({ hello }),
    setSnapshot: (snapshot) => set({ snapshot }),
  }));
}
