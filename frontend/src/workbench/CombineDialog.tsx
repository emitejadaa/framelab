import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { type ColumnInfo, useSummary } from "../data/hooks";
import { useRpc } from "../data/rpcContext";
import * as b from "../ops/build";
import type { Json, Kwargs, OpJson } from "../ops/build";
import { useAppStore } from "../state/context";
import { RpcError } from "../transport/rpc";
import { usePortalContainer } from "../ui/portal";
import { applyOp } from "./applyOp";
import { isTabular } from "./format";

const HOWS = ["inner", "left", "right", "outer", "cross"] as const;
type How = (typeof HOWS)[number];
const RELATIONS = ["one_to_one", "one_to_many", "many_to_one", "many_to_many"] as const;

/** A key on one side: a column position in that table's summary, or its index. */
type Side = number | "index" | null;
interface KeyPair {
  left: Side;
  right: Side;
}

interface Info {
  rows: Partial<Record<How, number>>;
  columns: Partial<Record<How, number>>;
  duplicates: { left: number; right: number } | null;
  relation: (typeof RELATIONS)[number] | null;
  mismatch: { left: string; right: string; left_dtype: string; right_dtype: string }[];
  common: Json[];
}

const same = (a: Json, c: ColumnInfo) => JSON.stringify(a) === JSON.stringify(c.label);

/** The merge keys as pandas keyword arguments (a single key is written without a list). */
function keyKwargs(pairs: KeyPair[], left: ColumnInfo[], right: ColumnInfo[]): Kwargs {
  const leftIndex = pairs.some((p) => p.left === "index");
  const rightIndex = pairs.some((p) => p.right === "index");
  const labels = (side: "left" | "right", cols: ColumnInfo[]) =>
    pairs.map((p) => p[side]).filter((s): s is number => typeof s === "number").map((i) => cols[i]?.label as Json);
  const one = (labels: Json[]) => (labels.length === 1 ? b.colRef(labels[0]) : b.listOf(labels.map(b.colRef)));
  const ll = labels("left", left);
  const rl = labels("right", right);
  const out: Kwargs = [];
  if (!leftIndex && !rightIndex && JSON.stringify(ll) === JSON.stringify(rl)) {
    if (ll.length) out.push(["on", one(ll)]);
    return out;
  }
  if (leftIndex) out.push(["left_index", b.lit(true)]);
  else if (ll.length) out.push(["left_on", one(ll)]);
  if (rightIndex) out.push(["right_index", b.lit(true)]);
  else if (rl.length) out.push(["right_on", one(rl)]);
  return out;
}

/** Combine two tables: merge on keys (with exact row counts per join type) or concatenate. */
export function CombineDialog() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const combining = useAppStore((s) => s.combining);
  const open = useAppStore((s) => s.openCombine);
  const select = useAppStore((s) => s.select);
  const nodes = useAppStore((s) => s.snapshot?.nodes);
  const tables = useMemo(() => (nodes ?? []).filter((n) => isTabular(n.kind) && n.kind !== "Index"), [nodes]);
  const leftNode = tables.find((n) => n.id === combining?.left) ?? null;
  const [rightId, setRightId] = useState<string | null>(null);
  const rightNode = tables.find((n) => n.id === rightId) ?? null;
  const leftSummary = useSummary(leftNode?.id ?? null, leftNode?.state ?? "");
  const rightSummary = useSummary(rightNode?.id ?? null, rightNode?.state ?? "");
  const leftCols = useMemo(() => leftSummary.data?.columns ?? [], [leftSummary.data]);
  const rightCols = useMemo(() => rightSummary.data?.columns ?? [], [rightSummary.data]);

  const [mode, setMode] = useState<"merge" | "concat">("merge");
  const [how, setHow] = useState<How>("inner");
  const [pairs, setPairs] = useState<KeyPair[] | null>(null); // null: not chosen yet (common columns)
  const [validate, setValidate] = useState<string>("");
  const [indicator, setIndicator] = useState(false);
  const [stack, setStack] = useState<string[]>([]);
  const [axis, setAxis] = useState<0 | 1>(0);
  const [ignoreIndex, setIgnoreIndex] = useState(false);
  const [info, setInfo] = useState<Info | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [forceable, setForceable] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRightId(combining?.right ?? null);
    setMode("merge");
    setHow("inner");
    setPairs(null);
    setValidate("");
    setIndicator(false);
    setStack(combining?.right ? [combining.right] : []);
    setAxis(0);
    setIgnoreIndex(false);
  }, [combining]);

  useEffect(() => {
    setPairs(null);
    setInfo(null);
  }, [rightId]);

  // The first answer (no keys) names the common columns: they become the proposed keys.
  useEffect(() => {
    if (pairs !== null || !info || !leftCols.length || !rightCols.length) return;
    const proposed = info.common
      .map((label) => ({ left: leftCols.findIndex((c) => same(label, c)), right: rightCols.findIndex((c) => same(label, c)) }))
      .filter((p) => p.left >= 0 && p.right >= 0);
    setPairs(proposed.length ? proposed : [{ left: null, right: null }]);
  }, [info, pairs, leftCols, rightCols]);

  const complete = (pairs ?? []).filter((p) => p.left !== null && p.right !== null);
  const usable = pairs !== null && complete.length === pairs.length && complete.length > 0;
  const keys = useMemo(() => (usable ? keyKwargs(complete, leftCols, rightCols) : []), [usable, complete, leftCols, rightCols]);
  const infoParams = useMemo(() => {
    if (!leftNode || !rightNode) return null;
    const params: Record<string, unknown> = { left: leftNode.id, right: rightNode.id };
    if (!usable) return params;
    for (const [key, value] of keys) {
      if (key === "left_index" || key === "right_index") params[key] = true;
      else params[key] = value.t === "list" ? (value.items as { label: Json }[]).map((v) => v.label) : [value.label];
    }
    if (params.on) {
      params.left_on = params.on;
      params.right_on = params.on;
      delete params.on;
    }
    return params;
  }, [leftNode, rightNode, usable, keys]);
  const infoKey = JSON.stringify(infoParams);

  useEffect(() => {
    if (!infoParams || leftNode?.state !== "ready" || rightNode?.state !== "ready") return;
    let alive = true;
    const timer = setTimeout(() => {
      rpc
        .request<Info>("node.combine_info", infoParams)
        .then(({ result }) => alive && setInfo(result))
        .catch((err) => alive && setProblem(err instanceof Error ? err.message : String(err)));
    }, 120);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [infoKey, rpc, leftNode?.state, rightNode?.state]);

  const op: OpJson | null = useMemo(() => {
    if (!leftNode) return null;
    if (mode === "concat") {
      const ids = [leftNode.id, ...tables.map((n) => n.id).filter((id) => stack.includes(id) && id !== leftNode.id)];
      if (ids.length < 2) return null;
      const kwargs: Kwargs = [];
      if (axis === 1) kwargs.push(["axis", b.lit(1)]);
      if (ignoreIndex) kwargs.push(["ignore_index", b.lit(true)]);
      return b.funcOp("concat", [b.listOf(ids.map(b.nodeRef))], kwargs);
    }
    if (!rightNode) return null;
    if (how !== "cross" && !usable) return null;
    const kwargs: Kwargs = how === "cross" ? [] : [...keys];
    kwargs.push(["how", b.lit(how)]);
    if (validate && how !== "cross") kwargs.push(["validate", b.lit(validate)]);
    if (indicator) kwargs.push(["indicator", b.lit(true)]);
    return { ...b.callOp(leftNode.id, "merge", kwargs), args: [b.nodeRef(rightNode.id)] };
  }, [leftNode, rightNode, mode, tables, stack, axis, ignoreIndex, how, usable, keys, validate, indicator]);

  useEffect(() => {
    setProblem(null);
    setForceable(false);
    if (!op) {
      setCode(null);
      return;
    }
    let alive = true;
    const timer = setTimeout(() => {
      rpc
        .request<{ code: string }>("op.preview", { op: op as unknown as Record<string, unknown> })
        .then(({ result }) => alive && setCode(result.code))
        .catch((err) => {
          if (!alive) return;
          setCode(null);
          setProblem(err instanceof Error ? err.message : String(err));
          setForceable(err instanceof RpcError && err.code === "too_big");
        });
    }, 150);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [op, rpc]);

  if (!combining || !leftNode || !portal) return null;
  const close = () => open(null);

  const create = async (next: OpJson, force = false) => {
    if (busy) return;
    setBusy(true);
    try {
      const created = await applyOp(rpc, next, { force });
      select(created.id);
      close();
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
      setForceable(err instanceof RpcError && err.code === "too_big");
    } finally {
      setBusy(false);
    }
  };

  /** A filter node with the rows whose key repeats on one side (to look at them first). */
  const repeated = (side: "left" | "right") => {
    const cols = side === "left" ? leftCols : rightCols;
    const target = side === "left" ? leftNode.id : rightNode?.id;
    const subset = complete.map((p) => p[side]).filter((s): s is number => typeof s === "number");
    if (!target || subset.length !== complete.length) return;
    const dup = b.method(b.thisFrame(), "duplicated", {
      kwargs: [
        ["subset", b.listOf(subset.map((i) => b.colRef(cols[i]?.label as Json)))],
        ["keep", b.lit(false)],
      ],
    });
    void create(b.filterOp(target, dup));
  };

  const sideSelect = (side: "left" | "right", k: number, value: Side) => {
    const cols = side === "left" ? leftCols : rightCols;
    return (
      <select
        className="fl-input"
        value={value === null ? "" : String(value)}
        data-testid={`combine-${side}-key-${k}`}
        onChange={(e) => {
          const v = e.target.value;
          const next: Side = v === "" ? null : v === "index" ? "index" : Number(v);
          setPairs((ps) => {
            const list = [...(ps ?? [])];
            list[k] = { ...list[k], [side]: next };
            return next === "index" ? [list[k]] : list; // the index is the whole key on its side
          });
        }}
      >
        <option value="">{t("combine.choose_key")}</option>
        <option value="index">{t("combine.index")}</option>
        {cols.map((c, i) => (
          <option key={`${i}-${c.text}`} value={i}>
            {c.text} · {c.dtype}
          </option>
        ))}
      </select>
    );
  };

  const count = (h: How) => (info?.rows[h] === undefined ? "" : ` — ${t("combine.rows", { count: info.rows[h] })}`);
  const usesIndex = (pairs ?? []).some((p) => p.left === "index" || p.right === "index");
  const others = tables.filter((n) => n.id !== leftNode.id);

  return createPortal(
    <div className="fl-overlay" onMouseDown={close}>
      <form
        className="fl-dialog fl-combine"
        data-testid="combine-dialog"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && close()}
        onSubmit={(e) => {
          e.preventDefault();
          if (op) void create(op);
        }}
      >
        <div className="fl-dialog-title">{t("combine.title", { name: leftNode.name })}</div>
        <div className="fl-segmented">
          {(["merge", "concat"] as const).map((m) => (
            <button key={m} type="button" data-active={mode === m} onClick={() => setMode(m)}>
              {t(`combine.${m}`)}
            </button>
          ))}
        </div>
        {mode === "merge" ? (
          <>
            <div className="fl-field">
              <div className="fl-field-label">{t("combine.with")}</div>
              <select
                className="fl-input"
                data-testid="combine-right"
                value={rightId ?? ""}
                onChange={(e) => setRightId(e.target.value || null)}
              >
                <option value="">{t("combine.choose_table")}</option>
                {tables.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.name}
                    {n.shape ? ` (${n.shape.join(" × ")})` : ""}
                  </option>
                ))}
              </select>
            </div>
            {rightNode && how !== "cross" ? (
              <div className="fl-field">
                <div className="fl-field-label">{t("combine.keys")}</div>
                {(pairs ?? []).map((p, k) => (
                  <div key={k} className="fl-combine-pair">
                    {sideSelect("left", k, p.left)}
                    <span className="fl-muted">=</span>
                    {sideSelect("right", k, p.right)}
                    {(pairs ?? []).length > 1 ? (
                      <button type="button" className="fl-btn fl-btn-quiet" onClick={() => setPairs((ps) => (ps ?? []).filter((_, i) => i !== k))}>
                        ×
                      </button>
                    ) : null}
                  </div>
                ))}
                {!usesIndex ? (
                  <button type="button" className="fl-btn fl-btn-quiet" onClick={() => setPairs((ps) => [...(ps ?? []), { left: null, right: null }])}>
                    + {t("combine.add_key")}
                  </button>
                ) : null}
              </div>
            ) : null}
            {rightNode ? (
              <div className="fl-field">
                <div className="fl-field-label">{t("combine.how")}</div>
                <select className="fl-input" data-testid="combine-how" value={how} onChange={(e) => setHow(e.target.value as How)}>
                  {HOWS.map((h) => (
                    <option key={h} value={h}>
                      {t(`combine.how_${h}`)}
                      {count(h)}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            {rightNode && how !== "cross" ? (
              <div className="fl-field">
                <div className="fl-field-label">{t("combine.validate")}</div>
                <select className="fl-input" value={validate} onChange={(e) => setValidate(e.target.value)}>
                  <option value="">{t("combine.validate_none")}</option>
                  {RELATIONS.map((r) => (
                    <option key={r} value={r}>
                      {t(`combine.relation_${r}`)}
                    </option>
                  ))}
                </select>
                {info?.relation ? (
                  <div className="fl-muted">{t("combine.relation_found", { relation: t(`combine.relation_${info.relation}`) })}</div>
                ) : null}
              </div>
            ) : null}
            {rightNode ? (
              <label className="fl-check">
                <input type="checkbox" checked={indicator} onChange={(e) => setIndicator(e.target.checked)} />
                {t("combine.indicator")}
              </label>
            ) : null}
            {info && info.mismatch.length ? (
              <div className="fl-warning">
                {info.mismatch.map((m) => t("combine.mismatch", { left: m.left, right: m.right, ldtype: m.left_dtype, rdtype: m.right_dtype })).join("\n")}
              </div>
            ) : null}
            {info?.duplicates && (info.duplicates.left || info.duplicates.right) && how !== "cross" ? (
              <div className="fl-warning" data-testid="combine-duplicates">
                {t("combine.duplicates", { left: info.duplicates.left, right: info.duplicates.right })}
                {!usesIndex ? (
                  <div className="fl-combine-actions">
                    {info.duplicates.left ? (
                      <button type="button" className="fl-btn fl-btn-quiet" onClick={() => repeated("left")}>
                        {t("combine.show_repeated", { name: leftNode.name })}
                      </button>
                    ) : null}
                    {info.duplicates.right && rightNode ? (
                      <button type="button" className="fl-btn fl-btn-quiet" onClick={() => repeated("right")}>
                        {t("combine.show_repeated", { name: rightNode.name })}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </>
        ) : (
          <>
            <div className="fl-field">
              <div className="fl-field-label">{t("combine.stack", { name: leftNode.name })}</div>
              <div className="fl-columns">
                {others.map((n) => (
                  <label key={n.id} className="fl-check">
                    <input
                      type="checkbox"
                      checked={stack.includes(n.id)}
                      onChange={(e) => setStack((s) => (e.target.checked ? [...s, n.id] : s.filter((id) => id !== n.id)))}
                    />
                    {n.name}
                    {n.shape ? <span className="fl-muted"> {n.shape.join(" × ")}</span> : null}
                  </label>
                ))}
              </div>
            </div>
            <div className="fl-segmented">
              {([0, 1] as const).map((a) => (
                <button key={a} type="button" data-active={axis === a} onClick={() => setAxis(a)}>
                  {t(a === 0 ? "combine.axis_rows" : "combine.axis_columns")}
                </button>
              ))}
            </div>
            <label className="fl-check">
              <input type="checkbox" checked={ignoreIndex} onChange={(e) => setIgnoreIndex(e.target.checked)} />
              {t("combine.ignore_index")}
            </label>
          </>
        )}
        <div className="fl-field-label">{t("form.code")}</div>
        <pre className="fl-code fl-code-preview" data-testid="combine-code">
          {code ?? "…"}
        </pre>
        {problem ? <div className="fl-form-error">{problem}</div> : null}
        <div className="fl-dialog-actions">
          <button type="button" className="fl-btn" onClick={close}>
            {t("form.cancel")}
          </button>
          {forceable ? (
            <button type="button" className="fl-btn fl-btn-quiet-danger" disabled={!op || busy} onClick={() => op && void create(op, true)}>
              {t("form.force")}
            </button>
          ) : null}
          <button type="submit" className="fl-btn fl-btn-primary" data-testid="combine-apply" disabled={!op || !code || busy}>
            {t("form.apply")}
          </button>
        </div>
      </form>
    </div>,
    portal,
  );
}
