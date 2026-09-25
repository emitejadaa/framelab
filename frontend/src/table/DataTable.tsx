import { useTranslation } from "react-i18next";
import type { DecodedWindow } from "../data/window";

/** Plain HTML rendering of one decoded Arrow window (the canvas grid arrives in M3). */
export function DataTable({ window, compact = false }: { window: DecodedWindow; compact?: boolean }) {
  const { t } = useTranslation();
  const { meta, index, cells } = window;
  return (
    <div className="fl-table-wrap" data-compact={compact ? "true" : "false"}>
      <table className="fl-table">
        <thead>
          <tr>
            {meta.index.map((col, k) => (
              <th key={`i${k}`} className="fl-th-index">
                {col.text ?? ""}
              </th>
            ))}
            {meta.columns.map((col, j) => (
              <th key={`c${j}`} title={col.fallback ?? undefined}>
                <div className="fl-th-name">
                  {col.text}
                  {col.fallback ? <span className="fl-badge">{t("table.as_text")}</span> : null}
                </div>
                <div className="fl-th-dtype">{col.dtype}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cells.map((row, i) => (
            <tr key={meta.offset + i}>
              {index[i].map((v, k) => (
                <td key={`i${k}`} className="fl-td-index">
                  {v ?? ""}
                </td>
              ))}
              {row.map((v, j) => (
                <td key={j} className={v === null ? "fl-null" : undefined}>
                  {v ?? "NaN"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {cells.length === 0 ? <div className="fl-muted fl-table-empty">{t("table.empty")}</div> : null}
    </div>
  );
}
