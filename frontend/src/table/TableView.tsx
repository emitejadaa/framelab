import { useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { type WindowSort, useSummary, useWindow } from "../data/hooks";
import { useRpc } from "../data/rpcContext";
import type { NodeInfo } from "../generated/protocol";
import * as b from "../ops/build";
import type { Json, OpJson } from "../ops/build";
import { useAppStore } from "../state/context";
import { copyText } from "../ui/clipboard";
import { usePortalContainer } from "../ui/portal";
import { applyOp } from "../workbench/applyOp";
import { shapeText } from "../workbench/format";
import { DataTable } from "./DataTable";

const PAGE = 100;

interface Menu {
  x: number;
  y: number;
  column: number;
  row?: number;
  text?: string | null;
}

export function TableView({ nodeId }: { nodeId: string }) {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const node = useAppStore((s) => s.snapshot?.nodes.find((n) => n.id === nodeId) ?? null);
  const showWorkbench = useAppStore((s) => s.showWorkbench);
  const openTable = useAppStore((s) => s.openTable);
  const select = useAppStore((s) => s.select);
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState<WindowSort | null>(null);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [created, setCreated] = useState<NodeInfo | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const win = useWindow(nodeId, node?.state ?? "", offset, PAGE, sort);
  const summary = useSummary(nodeId, node?.state ?? "");
  if (!node) return null;
  const total = win.data?.meta.nrows_total ?? node.shape?.[0] ?? 0;
  const last = Math.max(0, Math.floor((total - 1) / PAGE) * PAGE);
  const series = node.kind === "Series";
  const columns = summary.data?.columns ?? [];
  const label = (column: number) => columns[column]?.label as Json;
  const columnText = (column: number) => columns[column]?.text ?? "";

  const cycleSort = (column: number) => {
    setOffset(0);
    setSort((current) => {
      if (current?.column !== column) return { column, ascending: true };
      return current.ascending ? { column, ascending: false } : null;
    });
  };

  const create = async (op: OpJson | Promise<NodeInfo>) => {
    setMenu(null);
    setProblem(null);
    try {
      const info = op instanceof Promise ? await op : await applyOp(rpc, op);
      select(info.id);
      setCreated(info);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    }
  };

  const target = (column: number) => (series ? b.thisFrame() : b.getcol(label(column)));
  const sortStep = (): OpJson | null => {
    if (!sort) return null;
    const kwargs: b.Kwargs = series ? [] : [["by", b.colRef(label(sort.column))]];
    kwargs.push(["ascending", b.lit(sort.ascending)]);
    return b.callOp(nodeId, "sort_values", kwargs);
  };
  const filterCell = (row: number, column: number, mode: "eq" | "ne") =>
    rpc
      .request<{ node: NodeInfo }>("table.filter_cell", sort ? { id: nodeId, row, column, mode, sort } : { id: nodeId, row, column, mode })
      .then(({ result }) => result.node);

  const item = (key: string, text: string, run: () => void) => (
    <button key={key} type="button" className="fl-menu-item" onClick={run}>
      {text}
    </button>
  );

  const menuItems = (m: Menu) => {
    const out = [];
    if (m.row !== undefined) {
      out.push(item("eq", t("table.filter_eq", { value: m.text ?? "NaN" }), () => void create(filterCell(m.row as number, m.column, "eq"))));
      out.push(item("ne", t("table.filter_ne", { value: m.text ?? "NaN" }), () => void create(filterCell(m.row as number, m.column, "ne"))));
      out.push(
        item("copy", t("table.copy_value"), () => {
          void copyText(m.text ?? "");
          setMenu(null);
        }),
      );
      return out;
    }
    out.push(item("asc", t("table.sort_asc"), () => (setSort({ column: m.column, ascending: true }), setOffset(0), setMenu(null))));
    out.push(item("desc", t("table.sort_desc"), () => (setSort({ column: m.column, ascending: false }), setOffset(0), setMenu(null))));
    out.push(item("isna", t("table.keep_missing"), () => void create(b.filterOp(nodeId, b.method(target(m.column), "isna")))));
    out.push(item("notna", t("table.drop_missing"), () => void create(b.filterOp(nodeId, b.method(target(m.column), "notna")))));
    if (!series) {
      out.push(item("series", t("table.as_series"), () => void create(b.getitemOp(nodeId, label(m.column)))));
      out.push(item("drop", t("table.drop_column"), () => void create(b.callOp(nodeId, "drop", [["columns", b.listOf([b.colRef(label(m.column))])]]))));
    }
    return out;
  };

  return (
    <div className="fl-tableview">
      <div className="fl-toolbar">
        <button type="button" className="fl-btn" onClick={showWorkbench}>
          ← {t("tabs.workbench")}
        </button>
        <span className="fl-toolbar-title">{node.name}</span>
        <span className="fl-muted">{shapeText(node, t)}</span>
        {sort ? (
          <span className="fl-sort-note" data-testid="sort-note">
            {t("table.sorted_view", { column: columnText(sort.column), dir: sort.ascending ? "▲" : "▼" })}
            <button type="button" className="fl-btn" onClick={() => void create(sortStep() as OpJson)}>
              {t("table.make_step")}
            </button>
            <button type="button" className="fl-btn" title={t("table.clear_sort")} onClick={() => setSort(null)}>
              ×
            </button>
          </span>
        ) : null}
        <span className="fl-spacer" />
        <button type="button" className="fl-btn" disabled={offset === 0} onClick={() => setOffset(0)}>
          «
        </button>
        <button type="button" className="fl-btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
          ‹
        </button>
        <span className="fl-muted">
          {t("table.range", { from: total ? offset + 1 : 0, to: Math.min(offset + PAGE, total), total })}
        </span>
        <button type="button" className="fl-btn" disabled={offset >= last} onClick={() => setOffset(offset + PAGE)}>
          ›
        </button>
        <button type="button" className="fl-btn" disabled={offset >= last} onClick={() => setOffset(last)}>
          »
        </button>
      </div>
      {created ? (
        <div className="fl-created" data-testid="created-note">
          {t("table.created", { name: created.name })}
          <button type="button" className="fl-btn" onClick={() => openTable(created.id)}>
            {t("table.open_created")}
          </button>
          <button type="button" className="fl-btn" onClick={() => setCreated(null)}>
            ×
          </button>
        </div>
      ) : null}
      {problem ? <div className="fl-form-error fl-table-problem">{problem}</div> : null}
      <div className="fl-tableview-body">
        {win.error ? <div className="fl-form-error">{win.error}</div> : null}
        {win.data ? (
          <DataTable
            window={win.data}
            sort={sort}
            onSort={cycleSort}
            onColumnMenu={(column, e) => setMenu({ x: e.clientX, y: e.clientY, column })}
            onCellMenu={(row, column, e) =>
              setMenu({ x: e.clientX, y: e.clientY, column, row, text: (e.currentTarget as HTMLElement).textContent })
            }
          />
        ) : (
          <div className="fl-muted">{t("app.loading")}</div>
        )}
      </div>
      {menu && portal
        ? createPortal(
            <>
              <div className="fl-overlay-clear" onMouseDown={() => setMenu(null)} onContextMenu={(e) => e.preventDefault()} />
              <div
                className="fl-menu"
                role="menu"
                data-testid="table-menu"
                style={{ left: Math.min(menu.x, window.innerWidth - 280), top: Math.min(menu.y, window.innerHeight - 260) }}
              >
                <div className="fl-menu-title">{columnText(menu.column)}</div>
                <div className="fl-menu-scroll">{menuItems(menu)}</div>
              </div>
            </>,
            portal,
          )
        : null}
    </div>
  );
}
