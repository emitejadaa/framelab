import { useTranslation } from "react-i18next";
import { useSummary, useWindow } from "../data/hooks";
import { useAppStore } from "../state/context";
import { DataTable } from "../table/DataTable";
import { bytesText, isTabular, KIND_ICON, shapeText } from "./format";

export function Inspector() {
  const { t } = useTranslation();
  const node = useAppStore((s) => s.snapshot?.nodes.find((n) => n.id === s.selectedId) ?? null);
  const openTable = useAppStore((s) => s.openTable);
  const openMenu = useAppStore((s) => s.openMenu);
  const summary = useSummary(node?.id ?? null, node?.state ?? "");
  const preview = useWindow(node && isTabular(node.kind) ? node.id : null, node?.state ?? "", 0, 10);
  if (!node) return <aside className="fl-inspector fl-muted">{t("inspector.empty")}</aside>;
  const s = summary.data;
  return (
    <aside className="fl-inspector" data-testid="inspector">
      <div className="fl-inspector-head">
        <span className="fl-card-icon" data-kind={node.kind}>
          {KIND_ICON[node.kind]}
        </span>
        <div>
          <div className="fl-inspector-name">{node.name}</div>
          <div className="fl-muted">
            {node.kind} · {node.state === "ready" ? shapeText(node, t) : t(`node.state.${node.state}`)}
          </div>
        </div>
      </div>
      <div className="fl-inspector-actions">
        <button
          type="button"
          className="fl-btn fl-btn-primary"
          disabled={node.state !== "ready"}
          onClick={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            openMenu({ nodeId: node.id, x: r.left, y: r.bottom + 4 });
          }}
        >
          {t("inspector.operations")}
        </button>
        {isTabular(node.kind) ? (
          <button type="button" className="fl-btn" disabled={node.state !== "ready"} onClick={() => openTable(node.id)}>
            ▦ {t("menu.open_table")}
          </button>
        ) : null}
      </div>
      {node.error ? (
        <div className="fl-form-error">
          <strong>{node.error.type}</strong>: {node.error.message}
        </div>
      ) : null}
      {node.warnings?.length ? <div className="fl-warning">{node.warnings.join("\n")}</div> : null}
      {s?.kind === "Value" ? <pre className="fl-code">{s.repr}</pre> : null}
      {s?.kind === "GroupBy" ? (
        <div className="fl-kv">
          <span>{t("inspector.groups")}</span>
          <span>{s.ngroups}</span>
          <span>{t("inspector.keys")}</span>
          <span>{(s.keys ?? []).join(", ")}</span>
        </div>
      ) : null}
      {s?.memory_bytes !== undefined ? (
        <div className="fl-kv">
          <span>{t("inspector.memory")}</span>
          <span>{bytesText(s.memory_bytes)}</span>
        </div>
      ) : null}
      {preview.error ? <div className="fl-form-error">{preview.error}</div> : null}
      {preview.data ? (
        <>
          <div className="fl-section">{t("inspector.preview")}</div>
          <DataTable window={preview.data} compact />
        </>
      ) : null}
      {s?.columns && s.kind !== "GroupBy" ? (
        <>
          <div className="fl-section">{t("inspector.columns", { count: s.columns.length })}</div>
          <table className="fl-coltable">
            <tbody>
              {s.columns.map((c, i) => (
                <tr key={`${i}-${c.text}`}>
                  <td>{c.text}</td>
                  <td className="fl-muted">{c.dtype}</td>
                  <td className={c.nulls ? "fl-warn-text" : "fl-muted"}>
                    {c.nulls ? t("inspector.nulls", { count: c.nulls }) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </aside>
  );
}
