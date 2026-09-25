/**
 * Curated operations for M2a (the full, generated catalog arrives in M1b/M4).
 * Every op is plain data; Python validates and renders it into code.
 */
import type { ColumnInfo, Summary } from "../data/hooks";
import * as b from "../ops/build";
import type { Json, OpJson, Value } from "../ops/build";

export type Category =
  | "view"
  | "select"
  | "sort"
  | "clean"
  | "transform"
  | "group"
  | "aggregate"
  | "text"
  | "dates";

export const CATEGORY_ORDER: Category[] = [
  "view",
  "select",
  "sort",
  "clean",
  "transform",
  "group",
  "aggregate",
  "text",
  "dates",
];

export type FieldType = "number" | "text" | "column" | "columns" | "bool" | "choice" | "value";

export interface FieldSpec {
  key: string;
  type: FieldType;
  label: string;
  default?: unknown;
  options?: { value: string; label: string }[];
  optional?: boolean;
  /** for "value" fields: which column field decides how the text is parsed */
  columnField?: string;
}

export type Values = Record<string, unknown>;

export interface OpSpec {
  key: string;
  category: Category;
  label: string;
  kinds: string[];
  fields: FieldSpec[];
  available?: (summary: Summary) => boolean;
  build: (target: string, v: Values, s: Summary) => OpJson;
}

// ---- helpers ---------------------------------------------------------------------------
export const isNumeric = (dtype: string) => /^(u?int|Int|UInt|float|Float)/.test(dtype);
export const isText = (dtype: string) => dtype === "str" || dtype === "object" || dtype.startsWith("string");
export const isDate = (dtype: string) => dtype.startsWith("datetime64");
export const isBool = (dtype: string) => dtype === "bool" || dtype === "boolean";

const columns = (s: Summary): ColumnInfo[] => s.columns ?? [];
const onlyDtype = (s: Summary) => columns(s)[0]?.dtype ?? "";
const label = (s: Summary, index: unknown): Json => columns(s)[Number(index)]?.label as Json;
const labels = (s: Summary, indexes: unknown): Json[] =>
  (Array.isArray(indexes) ? indexes : []).map((i) => label(s, i));
const dtypeAt = (s: Summary, index: unknown): string => columns(s)[Number(index)]?.dtype ?? "";

export class ValueError extends Error {}

/** Parse what the user typed according to the column's dtype. */
export function parseValue(raw: unknown, dtype: string): Json {
  const text = String(raw ?? "").trim();
  if (isNumeric(dtype)) {
    if (text === "" || Number.isNaN(Number(text))) throw new ValueError("number");
    return Number(text);
  }
  if (isBool(dtype)) {
    if (!["true", "false", "True", "False", "1", "0"].includes(text)) throw new ValueError("bool");
    return ["true", "True", "1"].includes(text);
  }
  if (isDate(dtype)) {
    if (text === "" || Number.isNaN(Date.parse(text))) throw new ValueError("date");
    return { $: "ts", iso: text, tz: null };
  }
  return text;
}

const COMPARE = [
  { value: "==", label: "=" },
  { value: "!=", label: "≠" },
  { value: ">", label: ">" },
  { value: ">=", label: "≥" },
  { value: "<", label: "<" },
  { value: "<=", label: "≤" },
  { value: "contains", label: "ops.op.contains" },
  { value: "startswith", label: "ops.op.startswith" },
];

function condition(base: Value, op: string, raw: unknown, dtype: string): Value {
  if (op === "contains" || op === "startswith") {
    return b.method(base, op, {
      accessor: ["str"],
      args: [b.lit(String(raw ?? ""))],
      kwargs: op === "contains" ? [["na", b.lit(false)]] : [],
    });
  }
  return b.cmp(base, op, b.lit(parseValue(raw, dtype)));
}

const n = (key: string, def: number): FieldSpec => ({ key, type: "number", label: `ops.field.${key}`, default: def });
const DF = ["DataFrame"];
const SERIES = ["Series"];
const TABULAR = ["DataFrame", "Series"];
const GROUPBY = ["GroupBy"];

const simpleCall = (key: string, name: string, category: Category, kinds: string[]): OpSpec => ({
  key,
  category,
  label: `ops.${key}`,
  kinds,
  fields: [],
  build: (t) => b.callOp(t, name),
});

const GROUP_AGGS = ["sum", "mean", "median", "min", "max", "count", "size", "nunique", "first", "last"];
const NUMERIC_ONLY = new Set(["sum", "mean", "median", "min", "max"]);
const SERIES_AGGS = ["sum", "mean", "median", "min", "max", "count", "nunique", "std"];

export const OPS: OpSpec[] = [
  // ---- view ------------------------------------------------------------------------------
  {
    key: "head",
    category: "view",
    label: "ops.head",
    kinds: TABULAR,
    fields: [n("n", 5)],
    build: (t, v) => b.callOp(t, "head", [["n", b.lit(Number(v.n))]]),
  },
  {
    key: "tail",
    category: "view",
    label: "ops.tail",
    kinds: TABULAR,
    fields: [n("n", 5)],
    build: (t, v) => b.callOp(t, "tail", [["n", b.lit(Number(v.n))]]),
  },
  {
    key: "sample",
    category: "view",
    label: "ops.sample",
    kinds: TABULAR,
    fields: [n("n", 5), n("random_state", 0)],
    build: (t, v) =>
      b.callOp(t, "sample", [
        ["n", b.lit(Number(v.n))],
        ["random_state", b.lit(Number(v.random_state))],
      ]),
  },
  simpleCall("describe", "describe", "view", TABULAR),
  {
    key: "transpose",
    category: "view",
    label: "ops.transpose",
    kinds: DF,
    fields: [],
    build: (t) => b.attrOp(t, "T"),
  },
  // ---- select ----------------------------------------------------------------------------
  {
    key: "select_columns",
    category: "select",
    label: "ops.select_columns",
    kinds: DF,
    fields: [{ key: "columns", type: "columns", label: "ops.field.columns" }],
    build: (t, v, s) => b.getitemOp(t, b.columnsKey(labels(s, v.columns))),
  },
  {
    key: "column",
    category: "select",
    label: "ops.column",
    kinds: DF,
    fields: [{ key: "column", type: "column", label: "ops.field.column" }],
    build: (t, v, s) => b.getitemOp(t, label(s, v.column)),
  },
  {
    key: "filter",
    category: "select",
    label: "ops.filter",
    kinds: DF,
    fields: [
      { key: "column", type: "column", label: "ops.field.column" },
      { key: "operator", type: "choice", label: "ops.field.operator", options: COMPARE, default: "==" },
      { key: "value", type: "value", label: "ops.field.value", columnField: "column" },
    ],
    build: (t, v, s) =>
      b.filterOp(t, condition(b.getcol(label(s, v.column)), String(v.operator), v.value, dtypeAt(s, v.column))),
  },
  {
    key: "filter_series",
    category: "select",
    label: "ops.filter",
    kinds: SERIES,
    fields: [
      { key: "operator", type: "choice", label: "ops.field.operator", options: COMPARE, default: ">" },
      { key: "value", type: "value", label: "ops.field.value" },
    ],
    build: (t, v, s) => b.filterOp(t, condition(b.thisFrame(), String(v.operator), v.value, onlyDtype(s))),
  },
  {
    key: "filter_nulls",
    category: "select",
    label: "ops.filter_nulls",
    kinds: DF,
    fields: [
      { key: "column", type: "column", label: "ops.field.column" },
      {
        key: "which",
        type: "choice",
        label: "ops.field.which",
        options: [
          { value: "isna", label: "ops.which.isna" },
          { value: "notna", label: "ops.which.notna" },
        ],
        default: "isna",
      },
    ],
    build: (t, v, s) => b.filterOp(t, b.method(b.getcol(label(s, v.column)), String(v.which))),
  },
  // ---- sort --------------------------------------------------------------------------------
  {
    key: "sort",
    category: "sort",
    label: "ops.sort",
    kinds: DF,
    fields: [
      { key: "column", type: "column", label: "ops.field.by" },
      { key: "ascending", type: "bool", label: "ops.field.ascending", default: true },
    ],
    build: (t, v, s) =>
      b.callOp(t, "sort_values", [
        ["by", b.colRef(label(s, v.column))],
        ["ascending", b.lit(Boolean(v.ascending))],
      ]),
  },
  {
    key: "sort_series",
    category: "sort",
    label: "ops.sort",
    kinds: SERIES,
    fields: [{ key: "ascending", type: "bool", label: "ops.field.ascending", default: true }],
    build: (t, v) => b.callOp(t, "sort_values", [["ascending", b.lit(Boolean(v.ascending))]]),
  },
  simpleCall("sort_index", "sort_index", "sort", TABULAR),
  // ---- clean -------------------------------------------------------------------------------
  {
    key: "dropna",
    category: "clean",
    label: "ops.dropna",
    kinds: DF,
    fields: [{ key: "columns", type: "columns", label: "ops.field.subset", optional: true }],
    build: (t, v, s) => {
      const chosen = labels(s, v.columns);
      return b.callOp(t, "dropna", chosen.length ? [["subset", b.listOf(chosen.map(b.colRef))]] : []);
    },
  },
  simpleCall("dropna_series", "dropna", "clean", SERIES),
  {
    key: "fillna",
    category: "clean",
    label: "ops.fillna",
    kinds: DF,
    fields: [
      { key: "column", type: "column", label: "ops.field.column" },
      { key: "value", type: "value", label: "ops.field.fill_value", columnField: "column" },
    ],
    build: (t, v, s) =>
      b.callOp(t, "fillna", [
        ["value", b.dictOf([[b.colRef(label(s, v.column)), b.lit(parseValue(v.value, dtypeAt(s, v.column)))]])],
      ]),
  },
  {
    key: "drop_duplicates",
    category: "clean",
    label: "ops.drop_duplicates",
    kinds: DF,
    fields: [{ key: "columns", type: "columns", label: "ops.field.subset", optional: true }],
    build: (t, v, s) => {
      const chosen = labels(s, v.columns);
      return b.callOp(t, "drop_duplicates", chosen.length ? [["subset", b.listOf(chosen.map(b.colRef))]] : []);
    },
  },
  {
    key: "drop_columns",
    category: "clean",
    label: "ops.drop_columns",
    kinds: DF,
    fields: [{ key: "columns", type: "columns", label: "ops.field.columns" }],
    build: (t, v, s) => b.callOp(t, "drop", [["columns", b.listOf(labels(s, v.columns).map(b.colRef))]]),
  },
  // ---- transform ---------------------------------------------------------------------------
  {
    key: "rename",
    category: "transform",
    label: "ops.rename",
    kinds: DF,
    fields: [
      { key: "column", type: "column", label: "ops.field.column" },
      { key: "new_name", type: "text", label: "ops.field.new_name" },
    ],
    build: (t, v, s) =>
      b.callOp(t, "rename", [
        ["columns", b.dictOf([[b.colRef(label(s, v.column)), b.lit(String(v.new_name ?? ""))]])],
      ]),
  },
  {
    key: "astype",
    category: "transform",
    label: "ops.astype",
    kinds: DF,
    fields: [
      { key: "column", type: "column", label: "ops.field.column" },
      {
        key: "dtype",
        type: "choice",
        label: "ops.field.dtype",
        options: ["float64", "int64", "Int64", "str", "category", "bool", "boolean", "datetime64[ns]"].map((d) => ({
          value: d,
          label: d,
        })),
        default: "float64",
      },
    ],
    build: (t, v, s) =>
      b.callOp(t, "astype", [["dtype", b.dictOf([[b.colRef(label(s, v.column)), b.lit(String(v.dtype))]])]]),
  },
  {
    key: "new_column",
    category: "transform",
    label: "ops.new_column",
    kinds: DF,
    fields: [
      { key: "new_name", type: "text", label: "ops.field.new_name" },
      { key: "left", type: "column", label: "ops.field.left" },
      {
        key: "operator",
        type: "choice",
        label: "ops.field.operator",
        options: ["+", "-", "*", "/"].map((o) => ({ value: o, label: o })),
        default: "*",
      },
      { key: "right", type: "column", label: "ops.field.right" },
    ],
    build: (t, v, s) =>
      b.setitemOp(
        t,
        String(v.new_name ?? ""),
        b.arith(b.getcol(label(s, v.left)), String(v.operator), b.getcol(label(s, v.right))),
      ),
  },
  simpleCall("reset_index", "reset_index", "transform", TABULAR),
  simpleCall("to_frame", "to_frame", "transform", SERIES),
  // ---- group -------------------------------------------------------------------------------
  {
    key: "groupby",
    category: "group",
    label: "ops.groupby",
    kinds: DF,
    fields: [{ key: "column", type: "column", label: "ops.field.by" }],
    build: (t, v, s) => b.callOp(t, "groupby", [["by", b.colRef(label(s, v.column))]]),
  },
  simpleCall("value_counts", "value_counts", "group", SERIES),
  {
    key: "group_column",
    category: "select",
    label: "ops.group_column",
    kinds: GROUPBY,
    available: (s) => s.grouped === "DataFrame",
    fields: [{ key: "column", type: "column", label: "ops.field.column" }],
    build: (t, v, s) => b.getitemOp(t, label(s, v.column)),
  },
  ...GROUP_AGGS.map(
    (agg): OpSpec => ({
      key: `group_${agg}`,
      category: "aggregate",
      label: `ops.agg.${agg}`,
      kinds: GROUPBY,
      fields: [],
      build: (t, _v, s) =>
        b.callOp(
          t,
          agg,
          s.grouped === "DataFrame" && NUMERIC_ONLY.has(agg) ? [["numeric_only", b.lit(true)]] : [],
        ),
    }),
  ),
  ...SERIES_AGGS.map(
    (agg): OpSpec => ({
      key: `series_${agg}`,
      category: "aggregate",
      label: `ops.agg.${agg}`,
      kinds: SERIES,
      fields: [],
      available: (s) => agg === "count" || agg === "nunique" || isNumeric(onlyDtype(s)),
      build: (t) => b.callOp(t, agg),
    }),
  ),
  // ---- text / dates ----------------------------------------------------------------------------
  ...["lower", "upper", "strip", "len"].map(
    (m): OpSpec => ({
      key: `str_${m}`,
      category: "text",
      label: `ops.str.${m}`,
      kinds: SERIES,
      fields: [],
      available: (s) => isText(onlyDtype(s)),
      build: (t) => b.callOp(t, m, [], ["str"]),
    }),
  ),
  ...["year", "month", "day", "dayofweek"].map(
    (a): OpSpec => ({
      key: `dt_${a}`,
      category: "dates",
      label: `ops.dt.${a}`,
      kinds: SERIES,
      fields: [],
      available: (s) => isDate(onlyDtype(s)),
      build: (t) => b.attrOp(t, a, ["dt"]),
    }),
  ),
];

export function opsFor(kind: string, summary: Summary | null): OpSpec[] {
  return OPS.filter(
    (op) => op.kinds.includes(kind) && (!op.available || (summary !== null && op.available(summary))),
  );
}

export function opByKey(key: string): OpSpec | undefined {
  return OPS.find((op) => op.key === key);
}

export function defaults(op: OpSpec): Values {
  const out: Values = {};
  for (const f of op.fields) {
    if (f.default !== undefined) out[f.key] = f.default;
    else if (f.type === "column") out[f.key] = 0;
    else if (f.type === "columns") out[f.key] = [];
    else out[f.key] = "";
  }
  return out;
}
