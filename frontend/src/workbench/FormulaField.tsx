import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { ColumnInfo } from "../data/hooks";
import { useRpc } from "../data/rpcContext";
import type { Value } from "../ops/build";
import type { FormulaValue } from "./opsCatalog";

const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;
const OPERATORS = ["+", "-", "*", "/", "**", "(", ")"];
const FUNCTIONS: [string, string][] = [
  ["abs", "abs(|)"],
  ["round", "round(|, 2)"],
  ["sqrt", "sqrt(|)"],
  ["log", "log(|)"],
  ["fillna", "fillna(|, 0)"],
  ["where", "where(| > 0, 1, 0)"],
  ["maximum", "maximum(|, )"],
];

interface Parsed {
  ok: boolean;
  expr?: Value;
  message?: string;
}

/** A spreadsheet-like formula (`(precio - costo) * cantidad`), parsed by Python as you type. */
export function FormulaField({
  nodeId,
  columns,
  value,
  onChange,
}: {
  nodeId: string;
  columns: ColumnInfo[];
  value: FormulaValue;
  onChange(next: FormulaValue): void;
}) {
  const { t } = useTranslation();
  const rpc = useRpc();
  const area = useRef<HTMLTextAreaElement>(null);
  const latest = useRef(value.text);
  latest.current = value.text;
  const change = useRef(onChange);
  change.current = onChange;

  useEffect(() => {
    const text = value.text;
    if (!text.trim() || value.expr || value.message) return;
    const timer = setTimeout(() => {
      rpc
        .request<Parsed>("formula.parse", { id: nodeId, text })
        .then(({ result }) => {
          if (latest.current !== text) return; // the user kept typing
          const message = result.ok ? null : (result.message ?? "?");
          change.current({ text, expr: result.ok ? (result.expr ?? null) : null, message });
        })
        .catch((err) => {
          if (latest.current === text) change.current({ text, expr: null, message: String(err?.message ?? err) });
        });
    }, 180);
    return () => clearTimeout(timer);
  }, [value, nodeId, rpc]);

  const setText = (text: string) => onChange({ text, expr: null, message: null });

  /** Insert `snippet` at the cursor; a "|" in it marks where the cursor ends up. */
  const insert = (snippet: string) => {
    const el = area.current;
    const text = value.text;
    const start = el?.selectionStart ?? text.length;
    const end = el?.selectionEnd ?? text.length;
    const selected = text.slice(start, end);
    const [before, after = ""] = snippet.split("|");
    const pad = start > 0 && !/[\s(]$/.test(text.slice(0, start)) && !/^[)\],]/.test(before) ? " " : "";
    const piece = pad + before + selected + after;
    setText(text.slice(0, start) + piece + text.slice(end));
    requestAnimationFrame(() => {
      const pos = start + pad.length + before.length + selected.length;
      el?.focus();
      el?.setSelectionRange(pos, pos);
    });
  };

  const columnToken = (c: ColumnInfo) => (IDENT.test(c.text) ? c.text : `\`${c.text}\``);

  return (
    <div className="fl-formula">
      <textarea
        ref={area}
        className="fl-input fl-formula-input"
        rows={2}
        spellCheck={false}
        placeholder={t("formula.placeholder")}
        value={value.text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) e.preventDefault(); // Enter submits the form
        }}
      />
      <div className="fl-chips">
        {columns.map((c, i) => (
          <button key={`${i}-${c.text}`} type="button" className="fl-chip" title={c.dtype} onClick={() => insert(columnToken(c))}>
            {c.text}
          </button>
        ))}
      </div>
      <div className="fl-chips">
        {OPERATORS.map((op) => (
          <button key={op} type="button" className="fl-chip fl-chip-op" onClick={() => insert(op)}>
            {op}
          </button>
        ))}
        {FUNCTIONS.map(([name, snippet]) => (
          <button key={name} type="button" className="fl-chip fl-chip-fn" title={t(`formula.fn.${name}`)} onClick={() => insert(snippet)}>
            {name}()
          </button>
        ))}
      </div>
      <div className="fl-muted fl-formula-help">{t("formula.help")}</div>
    </div>
  );
}
