import { createStore } from "zustand/vanilla";
import type { HelloResult, SessionSnapshot } from "../generated/protocol";
import type { Member } from "../workbench/members";

export type ConnectionState = "connecting" | "ready" | "mismatch" | "error";
export type View =
  | { kind: "workbench" }
  | { kind: "table"; nodeId: string }
  | { kind: "plot"; figureId: string };

export interface MenuState {
  nodeId: string;
  x: number;
  y: number;
}

export interface FormState {
  nodeId: string;
  opKey: string;
}

export interface MemberFormState {
  nodeId: string;
  member: Member;
}

export interface AppState {
  connection: ConnectionState;
  error: string | null;
  hello: HelloResult | null;
  snapshot: SessionSnapshot | null;
  selectedId: string | null;
  view: View;
  tables: string[];
  plots: string[];
  menu: MenuState | null;
  form: FormState | null;
  deleting: string | null;
  renaming: string | null;
  browser: string | null;
  memberForm: MemberFormState | null;
  setConnection(connection: ConnectionState, error?: string | null): void;
  setHello(hello: HelloResult): void;
  setSnapshot(snapshot: SessionSnapshot): void;
  select(id: string | null): void;
  openTable(id: string): void;
  closeTable(id: string): void;
  openPlot(figureId: string): void;
  closePlot(figureId: string): void;
  showWorkbench(): void;
  openMenu(menu: MenuState): void;
  closeMenu(): void;
  openForm(form: FormState): void;
  closeForm(): void;
  askDelete(nodeId: string | null): void;
  askRename(nodeId: string | null): void;
  openBrowser(nodeId: string | null): void;
  openMemberForm(form: MemberFormState | null): void;
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
    plots: [],
    menu: null,
    form: null,
    deleting: null,
    renaming: null,
    browser: null,
    memberForm: null,
    setConnection: (connection, error = null) => set({ connection, error }),
    setHello: (hello) => set({ hello }),
    setSnapshot: (snapshot) =>
      set((s) => {
        // Python owns the graph: forget tabs and selections of deleted nodes and figures.
        const nodes = new Set(snapshot.nodes.map((n) => n.id));
        const figures = new Set(snapshot.figures.map((f) => f.id));
        const gone =
          (s.view.kind === "table" && !nodes.has(s.view.nodeId)) ||
          (s.view.kind === "plot" && !figures.has(s.view.figureId));
        const selected = s.selectedId && nodes.has(s.selectedId) ? s.selectedId : null;
        return {
          snapshot,
          selectedId: selected ?? snapshot.nodes[0]?.id ?? null,
          tables: s.tables.filter((id) => nodes.has(id)),
          plots: s.plots.filter((id) => figures.has(id)),
          view: gone ? { kind: "workbench" } : s.view,
          menu: s.menu && nodes.has(s.menu.nodeId) ? s.menu : null,
          form: s.form && nodes.has(s.form.nodeId) ? s.form : null,
          renaming: s.renaming && nodes.has(s.renaming) ? s.renaming : null,
          browser: s.browser && nodes.has(s.browser) ? s.browser : null,
          memberForm: s.memberForm && nodes.has(s.memberForm.nodeId) ? s.memberForm : null,
        };
      }),
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
    openPlot: (figureId) =>
      set((s) => ({
        plots: s.plots.includes(figureId) ? s.plots : [...s.plots, figureId],
        view: { kind: "plot", figureId },
        menu: null,
      })),
    closePlot: (figureId) =>
      set((s) => ({
        plots: s.plots.filter((f) => f !== figureId),
        view: s.view.kind === "plot" && s.view.figureId === figureId ? { kind: "workbench" } : s.view,
      })),
    showWorkbench: () => set({ view: { kind: "workbench" } }),
    openMenu: (menu) => set({ menu, selectedId: menu.nodeId }),
    closeMenu: () => set({ menu: null }),
    openForm: (form) => set({ form, menu: null }),
    closeForm: () => set({ form: null }),
    askDelete: (deleting) => set({ deleting, menu: null }),
    askRename: (renaming) => set({ renaming, menu: null }),
    openBrowser: (browser) => set({ browser, menu: null }),
    openMemberForm: (memberForm) => set({ memberForm, menu: null, browser: null }),
  }));
}
