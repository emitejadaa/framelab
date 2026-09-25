/** Small form controls for the Plotter panels. Text and numbers commit on Enter, blur or a pause. */
import { type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { type FieldInfo, type Ref, refKey, type SourceFields } from "./types";

const IDLE_MS = 700;

function useCommit<T>(value: T, commit: (v: T) => void) {
  const [draft, setDraft] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const commitRef = useRef(commit);
  commitRef.current = commit;
  useEffect(() => setDraft(value), [value]);
  useEffect(() => () => clearTimeout(timer.current), []);
  const change = (next: T, flush: (v: T) => void) => {
    setDraft(next);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => flush(next), IDLE_MS);
  };
  const now = (next: T, flush: (v: T) => void) => {
    clearTimeout(timer.current);
    flush(next);
  };
  return { draft, setDraft, change, now, commitRef };
}

export function TextBox({
  value,
  onCommit,
  placeholder,
  mono,
}: {
  value: string;
  onCommit(v: string): void;
  placeholder?: string;
  mono?: boolean;
}) {
  const { draft, change, now, commitRef } = useCommit(value, onCommit);
  const flush = (v: string) => v !== value && commitRef.current(v);
  return (
    <input
      className={mono ? "fl-input fl-mono" : "fl-input"}
      value={draft}
      placeholder={placeholder}
      onChange={(e) => change(e.target.value, flush)}
      onBlur={() => now(draft, flush)}
      onKeyDown={(e) => e.key === "Enter" && now(draft, flush)}
    />
  );
}

export function NumberBox({
  value,
  onCommit,
  min,
  max,
  step,
  placeholder,
  integer,
  allowEmpty,
}: {
  value: number | null;
  onCommit(v: number | null): void;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  integer?: boolean;
  allowEmpty?: boolean;
}) {
  const text = value === null || value === undefined ? "" : String(value);
  const [draft, setDraft] = useState(text);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const commit = useRef(onCommit);
  commit.current = onCommit;
  useEffect(() => setDraft(text), [text]);
  useEffect(() => () => clearTimeout(timer.current), []);
  const flush = (raw: string) => {
    clearTimeout(timer.current);
    const trimmed = raw.trim();
    if (trimmed === "") {
      if (allowEmpty && value !== null) commit.current(null);
      else if (!allowEmpty) setDraft(text);
      return;
    }
    let n = Number(trimmed.replace(",", "."));
    if (!Number.isFinite(n)) return setDraft(text);
    if (integer) n = Math.round(n);
    if (min !== undefined) n = Math.max(min, n);
    if (max !== undefined) n = Math.min(max, n);
    setDraft(String(n));
    if (n !== value) commit.current(n);
  };
  return (
    <input
      className="fl-input fl-number"
      inputMode="decimal"
      value={draft}
      placeholder={placeholder}
      step={step}
      onChange={(e) => {
        const next = e.target.value;
        setDraft(next);
        clearTimeout(timer.current);
        timer.current = setTimeout(() => flush(next), IDLE_MS);
      }}
      onBlur={() => flush(draft)}
      onKeyDown={(e) => e.key === "Enter" && flush(draft)}
    />
  );
}

export function Slider({
  value,
  onCommit,
  min,
  max,
  step,
}: {
  value: number;
  onCommit(v: number): void;
  min: number;
  max: number;
  step: number;
}) {
  const [live, setLive] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => setLive(value), [value]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <div className="fl-slider">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={live}
        onChange={(e) => {
          const n = Number(e.target.value);
          setLive(n);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => onCommit(n), 220);
        }}
      />
      <NumberBox value={live} min={min} max={max} step={step} onCommit={(n) => n !== null && onCommit(n)} />
    </div>
  );
}

export function Select<T extends string>({
  value,
  options,
  onChange,
  testId,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange(v: T): void;
  testId?: string;
}) {
  return (
    <select className="fl-input" value={value} data-testid={testId} onChange={(e) => onChange(e.target.value as T)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange(v: boolean): void; label: string }) {
  return (
    <label className="fl-check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

const HEX = /^#[0-9a-f]{6}$/i;

export function ColorBox({ value, onChange }: { value: string | null; onChange(v: string): void }) {
  const [live, setLive] = useState(value ?? "#3b82f6");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => setLive(value ?? "#3b82f6"), [value]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <div className="fl-color">
      <input
        type="color"
        value={HEX.test(live) ? live : "#3b82f6"}
        onChange={(e) => {
          const v = e.target.value;
          setLive(v);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => onChange(v), 200);
        }}
      />
      <TextBox value={value ?? ""} placeholder="auto" mono onCommit={(v) => v && onChange(v)} />
    </div>
  );
}

/** A labelled row; `hint` shows the matplotlib name, `onReset` clears a user-set value. */
export function Row({
  label,
  hint,
  onReset,
  children,
}: {
  label: string;
  hint?: string;
  onReset?: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <div className="fl-prow">
      <div className="fl-prow-label">
        <span>{label}</span>
        {hint ? <span className="fl-prow-hint">{hint}</span> : null}
        {onReset ? (
          <button type="button" className="fl-prow-reset" title={t("plot.reset")} onClick={onReset}>
            ↺
          </button>
        ) : null}
      </div>
      {children}
    </div>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="fl-psection">
      <div className="fl-psection-title">{title}</div>
      {children}
    </section>
  );
}

// ---- data references ----------------------------------------------------------------------
const KIND_MARK: Record<FieldInfo["kind"], string> = { num: "123", date: "📅", cat: "abc", bool: "✓", other: "?" };

export function fieldLabel(f: FieldInfo, t: (k: string, o?: Record<string, unknown>) => string): string {
  if ("index" in f.ref) return f.text ? t("plot.index_named", { name: f.text }) : t("plot.index");
  if ("values" in f.ref) return f.text ? t("plot.values_named", { name: f.text }) : t("plot.values");
  return f.text;
}

export function allFields(src: SourceFields | null, withIndex: boolean): FieldInfo[] {
  if (!src?.tabular) return [];
  return [...(withIndex && src.index ? [src.index] : []), ...src.fields];
}

export function RefSelect({
  fields,
  value,
  onChange,
  none,
  testId,
}: {
  fields: FieldInfo[];
  value: Ref | null;
  onChange(v: Ref | null): void;
  none?: string;
  testId?: string;
}) {
  const { t } = useTranslation();
  const key = refKey(value);
  const known = fields.some((f) => refKey(f.ref) === key);
  return (
    <select
      className="fl-input"
      data-testid={testId}
      value={key}
      onChange={(e) => onChange(e.target.value ? (JSON.parse(e.target.value) as Ref) : null)}
    >
      {none !== undefined ? <option value="">{none}</option> : null}
      {!known && key ? <option value={key}>{t("plot.missing_column")}</option> : null}
      {fields.map((f) => (
        <option key={refKey(f.ref)} value={refKey(f.ref)}>
          {fieldLabel(f, t)} · {KIND_MARK[f.kind]}
        </option>
      ))}
    </select>
  );
}

export function RefChecks({
  fields,
  value,
  onChange,
}: {
  fields: FieldInfo[];
  value: Ref[];
  onChange(v: Ref[]): void;
}) {
  const { t } = useTranslation();
  const chosen = new Set(value.map(refKey));
  return (
    <div className="fl-columns">
      {fields.map((f) => {
        const k = refKey(f.ref);
        return (
          <label key={k} className="fl-check">
            <input
              type="checkbox"
              checked={chosen.has(k)}
              onChange={(e) => {
                // keep the column order of the table, not the click order
                const next = fields.filter((g) => (refKey(g.ref) === k ? e.target.checked : chosen.has(refKey(g.ref))));
                onChange(next.map((g) => g.ref));
              }}
            />
            {fieldLabel(f, t)} <span className="fl-muted">{f.dtype}</span>
          </label>
        );
      })}
    </div>
  );
}
