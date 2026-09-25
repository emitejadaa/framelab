import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useSummary } from "../data/hooks";
import { useRpc } from "../data/rpcContext";
import type { Json, OpJson } from "../ops/build";
import { useAppStore } from "../state/context";
import { RpcError } from "../transport/rpc";
import { usePortalContainer } from "../ui/portal";
import { applyOp } from "./applyOp";
import { isTabular } from "./format";
import { buildMemberOp, displayName, type MemberParam, MemberFormError } from "./members";

const KERNELS = ["sum", "mean", "median", "min", "max", "count", "size", "nunique", "first", "last", "std", "var"];

function defaultText(value: Json | undefined): string {
  if (value === undefined || value === null) return "None";
  if (typeof value === "object" && !Array.isArray(value) && "$" in value) {
    return String((value as Record<string, Json>).$repr ?? JSON.stringify(value));
  }
  return JSON.stringify(value);
}

/** A form generated from a pandas member's parameters; only what the user sets is sent. */
export function MemberForm() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const form = useAppStore((s) => s.memberForm);
  const close = useAppStore((s) => s.openMemberForm);
  const select = useAppStore((s) => s.select);
  const nodes = useAppStore((s) => s.snapshot?.nodes);
  const node = nodes?.find((n) => n.id === form?.nodeId) ?? null;
  const summary = useSummary(node?.id ?? null, node?.state ?? "");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [code, setCode] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [forceable, setForceable] = useState(false);
  const [busy, setBusy] = useState(false);
  const member = form?.member;

  useEffect(() => {
    setValues({});
    setCode(null);
    setProblem(null);
  }, [member]);

  const columns = useMemo(() => summary.data?.columns ?? [], [summary.data]);
  const built: { op: OpJson | null; error: string | null } = useMemo(() => {
    if (!form || !member) return { op: null, error: null };
    try {
      return { op: buildMemberOp(form.nodeId, member, values, columns), error: null };
    } catch (err) {
      if (err instanceof MemberFormError) return { op: null, error: t(err.key, { name: err.param }) };
      return { op: null, error: String(err) };
    }
  }, [form, member, values, columns, t]);

  useEffect(() => {
    if (!built.op) {
      setCode(null);
      return;
    }
    let alive = true;
    const timer = setTimeout(() => {
      rpc
        .request<{ code: string }>("op.preview", { op: built.op as unknown as Record<string, unknown> })
        .then(({ result }) => {
          if (!alive) return;
          setCode(result.code);
          setProblem(null);
          setForceable(false);
        })
        .catch((err) => {
          if (!alive) return;
          setProblem(err instanceof Error ? err.message : String(err));
          setForceable(err instanceof RpcError && (err.code === "too_big" || err.code === "string_aggregation"));
        });
    }, 150);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [built.op, rpc]);

  if (!form || !member || !node || !portal) return null;
  const set = (key: string, value: unknown) => setValues((v) => ({ ...v, [key]: value }));
  const others = (nodes ?? []).filter((n) => n.id !== node.id && isTabular(n.kind));

  const submit = async (force = false) => {
    if (!built.op || busy) return;
    setBusy(true);
    try {
      const created = await applyOp(rpc, built.op, { force });
      select(created.id);
      close(null);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
      setForceable(err instanceof RpcError && (err.code === "too_big" || err.code === "string_aggregation"));
    } finally {
      setBusy(false);
    }
  };

  const control = (p: MemberParam) => {
    const value = values[p.name];
    const placeholder = p.required ? t("member.required") : t("member.default", { value: defaultText(p.default) });
    switch (p.widget) {
      case "bool":
        return (
          <select className="fl-input" value={String(value ?? "")} onChange={(e) => set(p.name, e.target.value)}>
            <option value="">{placeholder}</option>
            <option value="true">True</option>
            <option value="false">False</option>
          </select>
        );
      case "choice":
      case "axis": {
        const choices = p.choices?.length ? p.choices : [0, 1];
        return (
          <select className="fl-input" value={String(value ?? "")} onChange={(e) => set(p.name, e.target.value)}>
            <option value="">{placeholder}</option>
            {choices.map((c) => (
              <option key={JSON.stringify(c)} value={JSON.stringify(c)}>
                {c === null ? "None" : String(c)}
                {p.widget === "axis" && c === 0 ? " (index)" : p.widget === "axis" && c === 1 ? " (columns)" : ""}
              </option>
            ))}
          </select>
        );
      }
      case "column":
        return (
          <select className="fl-input" value={String(value ?? "")} onChange={(e) => set(p.name, e.target.value)}>
            <option value="">{placeholder}</option>
            {columns.map((c, i) => (
              <option key={`${i}-${c.text}`} value={i}>
                {c.text}
              </option>
            ))}
          </select>
        );
      case "columns": {
        if (!columns.length) break;
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
                    set(p.name, [...next].sort((a, b) => a - b));
                  }}
                />
                {c.text} <span className="fl-muted">{c.dtype}</span>
              </label>
            ))}
          </div>
        );
      }
      case "frame":
        return (
          <select className="fl-input" value={String(value ?? "")} onChange={(e) => set(p.name, e.target.value)}>
            <option value="">{p.required ? t("member.frame_none") : placeholder}</option>
            {others.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </select>
        );
      case "func":
        return (
          <>
            <input className="fl-input fl-mono" list={`kernels-${p.name}`} placeholder={placeholder} value={String(value ?? "")} onChange={(e) => set(p.name, e.target.value)} />
            <datalist id={`kernels-${p.name}`}>
              {KERNELS.map((k) => (
                <option key={k} value={k} />
              ))}
            </datalist>
          </>
        );
      default:
        break;
    }
    return (
      <input
        className="fl-input fl-mono"
        inputMode={p.widget === "int" || p.widget === "float" ? "decimal" : undefined}
        placeholder={placeholder}
        value={String(value ?? "")}
        onChange={(e) => set(p.name, e.target.value)}
      />
    );
  };

  const params = member.params.filter((p) => !p.variadic);
  return createPortal(
    <div className="fl-overlay" onMouseDown={() => close(null)}>
      <form
        className="fl-dialog fl-member-form"
        data-testid="member-form"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        onKeyDown={(e) => e.key === "Escape" && close(null)}
      >
        <div className="fl-dialog-title">
          <span className="fl-mono">{node.name}.{displayName(member)}()</span>
        </div>
        {member.summary ? <div className="fl-muted fl-member-summary">{member.summary}</div> : null}
        {params.length ? <div className="fl-muted">{t("member.help")}</div> : null}
        {params.map((p) => (
          <div key={p.name} className="fl-field">
            <div className="fl-field-label">
              <span className="fl-mono">{p.name}</span>
              {p.required ? <span className="fl-required"> *</span> : null}
              {p.annotation ? <span className="fl-prow-hint"> {p.annotation}</span> : null}
            </div>
            {control(p)}
          </div>
        ))}
        <div className="fl-field-label">{t("form.code")}</div>
        <pre className="fl-code fl-code-preview">{code ?? "…"}</pre>
        {built.error || problem ? <div className="fl-form-error">{built.error ?? problem}</div> : null}
        <div className="fl-dialog-actions">
          <button type="button" className="fl-btn" onClick={() => close(null)}>
            {t("form.cancel")}
          </button>
          {forceable ? (
            <button type="button" className="fl-btn fl-btn-quiet-danger" disabled={!built.op || busy} onClick={() => void submit(true)}>
              {t("form.force")}
            </button>
          ) : null}
          <button type="submit" className="fl-btn fl-btn-primary" disabled={!built.op || busy}>
            {t("form.apply")}
          </button>
        </div>
      </form>
    </div>,
    portal,
  );
}
