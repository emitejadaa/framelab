import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useSummary } from "../data/hooks";
import { useRpc } from "../data/rpcContext";
import { useAppStore } from "../state/context";
import { copyText } from "../ui/clipboard";
import { usePortalContainer } from "../ui/portal";
import { applyOp } from "./applyOp";
import { isTabular } from "./format";
import { CATEGORY_ORDER, type OpSpec, opsFor } from "./opsCatalog";
import { isPlottable, plotNode } from "./plotting";

export function NodeMenu() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const menu = useAppStore((s) => s.menu);
  const closeMenu = useAppStore((s) => s.closeMenu);
  const openForm = useAppStore((s) => s.openForm);
  const openTable = useAppStore((s) => s.openTable);
  const openPlot = useAppStore((s) => s.openPlot);
  const askDelete = useAppStore((s) => s.askDelete);
  const select = useAppStore((s) => s.select);
  const node = useAppStore((s) => s.snapshot?.nodes.find((n) => n.id === s.menu?.nodeId) ?? null);
  const summary = useSummary(node?.id ?? null, node?.state ?? "");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setQuery("");
    setError(null);
  }, [menu?.nodeId]);

  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeMenu();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menu, closeMenu]);

  if (!menu || !node || !portal) return null;
  const ready = node.state === "ready";
  const ops = ready ? opsFor(node.kind, summary.data) : [];
  const q = query.trim().toLowerCase();
  const visible = q ? ops.filter((op) => t(op.label).toLowerCase().includes(q) || op.key.includes(q)) : ops;

  const run = async (op: OpSpec) => {
    if (op.fields.length > 0) {
      openForm({ nodeId: node.id, opKey: op.key });
      return;
    }
    if (!summary.data) return;
    try {
      const created = await applyOp(rpc, op.build(node.id, {}, summary.data));
      select(created.id);
      closeMenu();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const plot = async () => {
    try {
      openPlot(await plotNode(rpc, node.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const copyCode = async () => {
    const { result } = await rpc.request<{ code: string }>("node.code", { id: node.id });
    await copyText(result.code);
    closeMenu();
  };

  const x = Math.min(menu.x, window.innerWidth - 280);
  const y = Math.min(menu.y, window.innerHeight - 420);
  return createPortal(
    <>
      <div className="fl-overlay-clear" onMouseDown={closeMenu} onContextMenu={(e) => e.preventDefault()} />
      <div className="fl-menu" style={{ left: x, top: y }} role="menu" onContextMenu={(e) => e.preventDefault()}>
        <div className="fl-menu-title">{node.name}</div>
        {ready && ops.length > 0 ? (
          <input
            autoFocus
            className="fl-input fl-menu-search"
            placeholder={t("menu.search")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && visible[0]) void run(visible[0]);
            }}
          />
        ) : null}
        <div className="fl-menu-scroll">
          {!ready ? <div className="fl-menu-note">{t(`node.state.${node.state}`)}</div> : null}
          {ready && summary.loading ? <div className="fl-menu-note">{t("app.loading")}</div> : null}
          {CATEGORY_ORDER.map((cat) => {
            const items = visible.filter((op) => op.category === cat);
            if (!items.length) return null;
            return (
              <div key={cat} className="fl-menu-group">
                <div className="fl-menu-heading">{t(`ops.category.${cat}`)}</div>
                {items.map((op) => (
                  <button key={op.key} type="button" className="fl-menu-item" onClick={() => void run(op)}>
                    {t(op.label)}
                    {op.fields.length ? <span className="fl-menu-more">…</span> : null}
                  </button>
                ))}
              </div>
            );
          })}
          <div className="fl-menu-group">
            <div className="fl-menu-heading">{t("menu.node")}</div>
            {ready && isTabular(node.kind) ? (
              <button type="button" className="fl-menu-item" onClick={() => openTable(node.id)}>
                ▦ {t("menu.open_table")}
              </button>
            ) : null}
            {ready && isPlottable(node.kind) ? (
              <button type="button" className="fl-menu-item" onClick={() => void plot()}>
                ▟ {t("menu.plot")}
              </button>
            ) : null}
            <button type="button" className="fl-menu-item" onClick={() => void copyCode()}>
              {t("menu.copy_code")}
            </button>
            {node.parents.length > 0 ? (
              <button type="button" className="fl-menu-item fl-menu-danger" onClick={() => askDelete(node.id)}>
                {t("menu.delete")}
                <span className="fl-menu-more">Supr</span>
              </button>
            ) : null}
          </div>
          {error ? <div className="fl-menu-error">{error}</div> : null}
        </div>
      </div>
    </>,
    portal,
  );
}
