import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useSummary } from "../data/hooks";
import { useRpc } from "../data/rpcContext";
import type { OpJson } from "../ops/build";
import { useAppStore } from "../state/context";
import { usePortalContainer } from "../ui/portal";
import { applyOp } from "./applyOp";
import { FormulaField } from "./FormulaField";
import { defaults, type FieldSpec, type FormulaValue, opByKey, ValueError, type Values } from "./opsCatalog";

interface Preview {
  name: string;
  code: string;
}

export function OpForm() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const form = useAppStore((s) => s.form);
  const closeForm = useAppStore((s) => s.closeForm);
  const select = useAppStore((s) => s.select);
  const node = useAppStore((s) => s.snapshot?.nodes.find((n) => n.id === s.form?.nodeId) ?? null);
  const op = form ? opByKey(form.opKey) : undefined;
  const summary = useSummary(node?.id ?? null, node?.state ?? "");
  const [values, setValues] = useState<Values>({});
  const [preview, setPreview] = useState<Preview | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (op) setValues(defaults(op));
    setPreview(null);
    setProblem(null);
  }, [op]);

  const built: { op: OpJson | null; error: string | null } = useMemo(() => {
    if (!op || !node || !summary.data) return { op: null, error: null };
    for (const f of op.fields) {
      const v = values[f.key];
      if (f.type === "formula") {
        const formula = v as FormulaValue | undefined;
        if (!formula?.text.trim()) return { op: null, error: t("form.missing", { field: t(f.label) }) };
        if (formula.message) return { op: null, error: formula.message };
        if (!formula.expr) return { op: null, error: null }; // still parsing
        continue;
      }
      if (!f.optional && (v === "" || v === undefined || (Array.isArray(v) && v.length === 0))) {
        return { op: null, error: t("form.missing", { field: t(f.label) }) };
      }
    }
    try {
      return { op: op.build(node.id, values, summary.data), error: null };
    } catch (err) {
      if (err instanceof ValueError) return { op: null, error: t(`form.bad_${err.message}`) };
      return { op: null, error: String(err) };
    }
  }, [op, node, summary.data, values, t]);

  useEffect(() => {
    if (!built.op) {
      setPreview(null);
      return;
    }
    let alive = true;
    const timer = setTimeout(() => {
      rpc
        .request<Preview>("op.preview", { op: built.op as unknown as Record<string, unknown> })
        .then(({ result }) => {
          if (alive) {
            setPreview(result);
            setProblem(null);
          }
        })
        .catch((err) => alive && setProblem(err instanceof Error ? err.message : String(err)));
    }, 120);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [built.op, rpc]);

  if (!form || !op || !node || !portal) return null;
  const columns = summary.data?.columns ?? [];

  const submit = async () => {
    if (!built.op || busy) return;
    setBusy(true);
    try {
      const created = await applyOp(rpc, built.op);
      select(created.id);
      closeForm();
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const set = (key: string, value: unknown) => setValues((v) => ({ ...v, [key]: value }));
  const setFormula = (key: string) => (next: FormulaValue) => set(key, next);

  const field = (f: FieldSpec) => {
    const value = values[f.key];
    switch (f.type) {
      case "number":
        return <input className="fl-input" type="number" value={String(value ?? "")} onChange={(e) => set(f.key, e.target.value)} />;
      case "text":
      case "value":
        return <input className="fl-input" value={String(value ?? "")} onChange={(e) => set(f.key, e.target.value)} />;
      case "bool":
        return (
          <label className="fl-check">
            <input type="checkbox" checked={Boolean(value)} onChange={(e) => set(f.key, e.target.checked)} />
            {t("form.yes")}
          </label>
        );
      case "choice":
        return (
          <select className="fl-input" value={String(value ?? "")} onChange={(e) => set(f.key, e.target.value)}>
            {(f.options ?? []).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label.includes(".") ? t(o.label) : o.label}
              </option>
            ))}
          </select>
        );
      case "column":
        return (
          <select className="fl-input" value={String(value ?? 0)} onChange={(e) => set(f.key, Number(e.target.value))}>
            {columns.map((c, i) => (
              <option key={`${i}-${c.text}`} value={i}>
                {c.text} · {c.dtype}
              </option>
            ))}
          </select>
        );
      case "formula":
        return (
          <FormulaField
            nodeId={node.id}
            columns={columns}
            value={(value as FormulaValue) ?? { text: "", expr: null, message: null }}
            onChange={setFormula(f.key)}
          />
        );
      case "columns": {
        const chosen = new Set(Array.isArray(value) ? (value as number[]) : []);
        return (
          <div className="fl-columns">
            {columns.map((c, i) => (
              <label key={`${i}-${c.text}`} className="fl-check">
                <input
                  type="checkbox"
                  checked={chosen.has(i)}
                  onChange={(e) => {
                    const next = new Set(chosen);
                    if (e.target.checked) next.add(i);
                    else next.delete(i);
                    set(f.key, [...next].sort((a, b) => a - b));
                  }}
                />
                {c.text} <span className="fl-muted">{c.dtype}</span>
              </label>
            ))}
          </div>
        );
      }
    }
  };

  return createPortal(
    <div className="fl-overlay" onMouseDown={closeForm}>
      <form
        className="fl-dialog"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        onKeyDown={(e) => e.key === "Escape" && closeForm()}
      >
        <div className="fl-dialog-title">
          {t(op.label)} <span className="fl-muted">· {node.name}</span>
        </div>
        {summary.loading ? <div className="fl-muted">{t("app.loading")}</div> : null}
        {op.fields.map((f) => (
          <div key={f.key} className="fl-field">
            <div className="fl-field-label">
              {t(f.label)}
              {f.optional ? <span className="fl-muted"> · {t("form.optional")}</span> : null}
            </div>
            {field(f)}
          </div>
        ))}
        <div className="fl-field-label">{t("form.code")}</div>
        <pre className="fl-code fl-code-preview">{preview ? preview.code : "…"}</pre>
        {built.error || problem ? <div className="fl-form-error">{built.error ?? problem}</div> : null}
        <div className="fl-dialog-actions">
          <button type="button" className="fl-btn" onClick={closeForm}>
            {t("form.cancel")}
          </button>
          <button type="submit" className="fl-btn fl-btn-primary" disabled={!built.op || busy}>
            {t("form.apply")}
          </button>
        </div>
      </form>
    </div>,
    portal,
  );
}
