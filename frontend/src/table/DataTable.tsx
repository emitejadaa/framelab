import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import type { WindowSort } from "../data/hooks";
import type { DecodedWindow } from "../data/window";

interface Handlers {
  sort?: WindowSort | null;
  onSort?(column: number): void;
  onColumnMenu?(column: number, event: MouseEvent): void;
  onCellMenu?(row: number, column: number, event: MouseEvent): void;
}

/** Plain HTML rendering of one decoded Arrow window (the canvas grid arrives in M3). */
export function DataTable({
  window,
  compact = false,
  sort = null,
  onSort,
  onColumnMenu,
  onCellMenu,
}: { window: DecodedWindow; compact?: boolean } & Handlers) {
  const { t } = useTranslation();
  const { meta, index, cells } = window;
  const first = meta.col_start ?? 0;
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
            {meta.columns.map((col, j) => {
              const position = first + j;
              const sorted = sort?.column === position ? (sort.ascending ? "▲" : "▼") : null;
              return (
                <th
                  key={`c${j}`}
                  title={col.fallback ?? undefined}
                  data-sortable={onSort ? "true" : "false"}
                  onClick={onSort ? () => onSort(position) : undefined}
                  onContextMenu={
                    onColumnMenu
                      ? (e) => {
                          e.preventDefault();
                          onColumnMenu(position, e);
                        }
                      : undefined
                  }
                >
                  <div className="fl-th-name">
                    {col.text}
                    {sorted ? <span className="fl-th-sort">{sorted}</span> : null}
                    {col.fallback ? <span className="fl-badge">{t("table.as_text")}</span> : null}
                  </div>
                  <div className="fl-th-dtype">{col.dtype}</div>
                </th>
              );
            })}
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
                <td
                  key={j}
                  className={v === null ? "fl-null" : undefined}
                  onContextMenu={
                    onCellMenu
                      ? (e) => {
                          e.preventDefault();
                          onCellMenu(meta.offset + i, first + j, e);
                        }
                      : undefined
                  }
                >
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
