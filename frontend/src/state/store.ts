import { createStore } from "zustand/vanilla";
import type { HelloResult, SessionSnapshot } from "../generated/protocol";

export type ConnectionState = "connecting" | "ready" | "mismatch" | "error";
export type View = { kind: "workbench" } | { kind: "table"; nodeId: string };

export interface MenuState {
  nodeId: string;
  x: number;
  y: number;
}

export interface FormState {
  nodeId: string;
  opKey: string;
}

export interface AppState {
  connection: ConnectionState;
  error: string | null;
  hello: HelloResult | null;
  snapshot: SessionSnapshot | null;
  selectedId: string | null;
  view: View;
  tables: string[];
  menu: MenuState | null;
  form: FormState | null;
  setConnection(connection: ConnectionState, error?: string | null): void;
  setHello(hello: HelloResult): void;
  setSnapshot(snapshot: SessionSnapshot): void;
  select(id: string | null): void;
  openTable(id: string): void;
  closeTable(id: string): void;
  showWorkbench(): void;
  openMenu(menu: MenuState): void;
  closeMenu(): void;
  openForm(form: FormState): void;
  closeForm(): void;
}

export type AppStore = ReturnType<typeof createAppStore>;

/** One store per mounted UI (never a module singleton: two widgets can share a page). */
export function createAppStore() {
  return createStore<AppState>()((set) => ({
    connection: "connecting",
    error: null,
    hello: null,
    snapshot: null,
    selectedId: null,
    view: { kind: "workbench" },
    tables: [],
    menu: null,
    form: null,
    setConnection: (connection, error = null) => set({ connection, error }),
    setHello: (hello) => set({ hello }),
    setSnapshot: (snapshot) =>
      set((s) => ({
        snapshot,
        selectedId: s.selectedId ?? snapshot.nodes[0]?.id ?? null,
      })),
    select: (selectedId) => set({ selectedId }),
    openTable: (id) =>
      set((s) => ({
        tables: s.tables.includes(id) ? s.tables : [...s.tables, id],
        view: { kind: "table", nodeId: id },
        selectedId: id,
        menu: null,
      })),
    closeTable: (id) =>
      set((s) => ({
        tables: s.tables.filter((t) => t !== id),
        view: s.view.kind === "table" && s.view.nodeId === id ? { kind: "workbench" } : s.view,
      })),
    showWorkbench: () => set({ view: { kind: "workbench" } }),
    openMenu: (menu) => set({ menu, selectedId: menu.nodeId }),
    closeMenu: () => set({ menu: null }),
    openForm: (form) => set({ form, menu: null }),
    closeForm: () => set({ form: null }),
  }));
}
