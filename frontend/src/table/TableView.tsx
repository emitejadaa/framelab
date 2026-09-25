import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWindow } from "../data/hooks";
import { useAppStore } from "../state/context";
import { shapeText } from "../workbench/format";
import { DataTable } from "./DataTable";

const PAGE = 100;

export function TableView({ nodeId }: { nodeId: string }) {
  const { t } = useTranslation();
  const node = useAppStore((s) => s.snapshot?.nodes.find((n) => n.id === nodeId) ?? null);
  const showWorkbench = useAppStore((s) => s.showWorkbench);
  const [offset, setOffset] = useState(0);
  const win = useWindow(nodeId, node?.state ?? "", offset, PAGE);
  if (!node) return null;
  const total = win.data?.meta.nrows_total ?? node.shape?.[0] ?? 0;
  const last = Math.max(0, Math.floor((total - 1) / PAGE) * PAGE);
  return (
    <div className="fl-tableview">
      <div className="fl-toolbar">
        <button type="button" className="fl-btn" onClick={showWorkbench}>
          ← {t("tabs.workbench")}
        </button>
        <span className="fl-toolbar-title">{node.name}</span>
        <span className="fl-muted">{shapeText(node, t)}</span>
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
      <div className="fl-tableview-body">
        {win.error ? <div className="fl-form-error">{win.error}</div> : null}
        {win.data ? <DataTable window={win.data} /> : <div className="fl-muted">{t("app.loading")}</div>}
      </div>
    </div>
  );
}
