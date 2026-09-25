/** Op JSON builders mirroring framelab.ops (Python validates everything again). */

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Value = { [key: string]: Json };
export type Kwargs = [string, Value][];

export interface OpJson {
  schema_v: 1;
  kind: "call" | "attr" | "getitem" | "filter" | "setitem" | "func";
  target: string | null;
  name: string;
  accessor: string[];
  args: Value[];
  kwargs: Kwargs;
  key?: Json;
  expr?: Value;
}

/** A literal; `v` must already be a JSON scalar or an encoded scalar ({"$": ...}). */
export const lit = (v: Json): Value => ({ t: "lit", v });
/** A column label of the target frame; `label` is the encoded label from node.summary. */
export const colRef = (label: Json): Value => ({ t: "col", label });
export const listOf = (items: Value[]): Value => ({ t: "list", items });
export const dictOf = (pairs: [Value, Value][]): Value => ({ t: "dict", items: pairs });
export const fn = (name: string, ns: "str" | "np" = "str"): Value => ({ t: "func", name, ns });
/** Another node (for example the right-hand table of a merge). */
export const nodeRef = (id: string): Value => ({ t: "node", id });
export const thisFrame = (): Value => ({ t: "this" });
export const getcol = (label: Json): Value => ({ t: "getcol", base: thisFrame(), label });
export const method = (
  base: Value,
  name: string,
  opts: { accessor?: string[]; args?: Value[]; kwargs?: Kwargs } = {},
): Value => ({
  t: "call",
  base,
  name,
  accessor: opts.accessor ?? [],
  args: opts.args ?? [],
  kwargs: opts.kwargs ?? [],
});
export const cmp = (left: Value, op: string, right: Value): Value => ({ t: "cmp", op, left, right });
export const arith = (left: Value, op: string, right: Value): Value => ({ t: "arith", op, left, right });

function base(kind: OpJson["kind"], target: string | null, name = ""): OpJson {
  return { schema_v: 1, kind, target, name, accessor: [], args: [], kwargs: [] };
}

export const callOp = (target: string, name: string, kwargs: Kwargs = [], accessor: string[] = []): OpJson => ({
  ...base("call", target, name),
  kwargs,
  accessor,
});
export const attrOp = (target: string, name: string, accessor: string[] = []): OpJson => ({
  ...base("attr", target, name),
  accessor,
});
export const getitemOp = (target: string, key: Json): OpJson => ({ ...base("getitem", target), key });
export const columnsKey = (labels: Json[]): Json => ({ $: "list", items: labels });
export const filterOp = (target: string, cond: Value): OpJson => ({ ...base("filter", target), expr: cond });
export const setitemOp = (target: string, label: Json, value: Value): OpJson => ({
  ...base("setitem", target),
  key: label,
  expr: value,
});
