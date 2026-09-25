import { useTranslation } from "react-i18next";
import { useAppStore } from "../state/context";
import { TableView } from "../table/TableView";
import { PlotView } from "../plot/PlotView";
import { Canvas } from "../workbench/Canvas";
import { CodePanel } from "../workbench/CodePanel";
import { DeleteDialog } from "../workbench/DeleteDialog";
import { RenameDialog } from "../workbench/RenameDialog";
import { Inspector } from "../workbench/Inspector";
import { NodeMenu } from "../workbench/NodeMenu";
import { OpForm } from "../workbench/OpForm";
import { Loader } from "./Loader";

function Tabs() {
  const { t } = useTranslation();
  const view = useAppStore((s) => s.view);
  const tables = useAppStore((s) => s.tables);
  const plots = useAppStore((s) => s.plots);
  const nodes = useAppStore((s) => s.snapshot?.nodes ?? []);
  const figures = useAppStore((s) => s.snapshot?.figures ?? []);
  const openPlot = useAppStore((s) => s.openPlot);
  const closePlot = useAppStore((s) => s.closePlot);
  const showWorkbench = useAppStore((s) => s.showWorkbench);
  const openTable = useAppStore((s) => s.openTable);
  const closeTable = useAppStore((s) => s.closeTable);
  return (
    <nav className="fl-tabs">
      <span className="fl-brand">framelab</span>
      <button type="button" className="fl-tab" data-active={view.kind === "workbench" ? "true" : "false"} onClick={showWorkbench}>
        ⌂ {t("tabs.workbench")}
      </button>
      {tables.map((id) => {
        const name = nodes.find((n) => n.id === id)?.name ?? id;
        const active = view.kind === "table" && view.nodeId === id;
        return (
          <span key={id} className="fl-tab" data-active={active ? "true" : "false"}>
            <button type="button" onClick={() => openTable(id)}>
              ▦ {name}
            </button>
            <button type="button" className="fl-tab-close" aria-label={t("tabs.close")} onClick={() => closeTable(id)}>
              ×
            </button>
          </span>
        );
      })}
      {plots.map((id) => {
        const name = figures.find((f) => f.id === id)?.name ?? id;
        const active = view.kind === "plot" && view.figureId === id;
        return (
          <span key={id} className="fl-tab" data-active={active ? "true" : "false"}>
            <button type="button" onClick={() => openPlot(id)}>
              ▟ {name}
            </button>
            <button type="button" className="fl-tab-close" aria-label={t("tabs.close")} onClick={() => closePlot(id)}>
              ×
            </button>
          </span>
        );
      })}
    </nav>
  );
}

export function Shell() {
  const { t } = useTranslation();
  const connection = useAppStore((s) => s.connection);
  const error = useAppStore((s) => s.error);
  const snapshot = useAppStore((s) => s.snapshot);
  const view = useAppStore((s) => s.view);

  if (connection === "connecting" && !snapshot) return <Loader label={t("app.connecting")} />;
  if (connection === "mismatch" || connection === "error" || !snapshot) {
    return (
      <div className="fl:flex fl:h-full fl:flex-col fl:items-center fl:justify-center fl:gap-2 fl:p-6">
        <p style={{ color: "var(--fl-danger)" }}>
          {connection === "mismatch" ? t("app.protocolMismatch") : t("app.error")}
        </p>
        {error ? <pre className="fl-muted">{error}</pre> : null}
      </div>
    );
  }
  return (
    <div className="fl-shell">
      <Tabs />
      {view.kind === "table" ? (
        <TableView key={view.nodeId} nodeId={view.nodeId} />
      ) : view.kind === "plot" ? (
        <PlotView key={view.figureId} figureId={view.figureId} />
      ) : (
        <div className="fl-workbench">
          <div className="fl-center">
            <Canvas />
            <CodePanel />
          </div>
          <Inspector />
        </div>
      )}
      {connection === "connecting" ? <div className="fl-banner">{t("app.reconnecting")}</div> : null}
      <NodeMenu />
      <OpForm />
      <DeleteDialog />
      <RenameDialog />
    </div>
  );
}
