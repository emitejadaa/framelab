/** pandas members a node offers (from Python's catalog) and ops built from their forms. */
import { useEffect, useState } from "react";
import type { ColumnInfo } from "../data/hooks";
import { useRpc } from "../data/rpcContext";
import * as b from "../ops/build";
import type { Json, OpJson, Value } from "../ops/build";

export interface MemberParam {
  name: string;
  widget: string;
  required: boolean;
  annotation: string;
  default?: Json;
  choices?: Json[];
  variadic?: string;
}

export interface Member {
  owner: string;
  name: string;
  kind: "method" | "property";
  category: string;
  summary: string;
  params: MemberParam[];
  returns: string;
  accessor: string[];
}

/** node.members, fetched once per node and state. */
export function useMembers(nodeId: string | null, state: string): { members: Member[]; loading: boolean } {
  const rpc = useRpc();
  const [out, setOut] = useState<{ members: Member[]; loading: boolean }>({ members: [], loading: false });
  useEffect(() => {
    if (!nodeId || state !== "ready") {
      setOut({ members: [], loading: false });
      return;
    }
    let alive = true;
    setOut((o) => ({ ...o, loading: true }));
    rpc
      .request<{ members: Member[] }>("node.members", { id: nodeId })
      .then(({ result }) => alive && setOut({ members: result.members, loading: false }))
      .catch(() => alive && setOut({ members: [], loading: false }));
    return () => {
      alive = false;
    };
  }, [rpc, nodeId, state]);
  return out;
}

/** What the user typed, as a JSON value: "" is unset; true/false, None/null, numbers and JSON lists
 * or objects are recognised; anything else stays text. */
export function parseLiteral(text: string): { set: boolean; value?: Json } {
  const raw = text.trim();
  if (raw === "") return { set: false };
  if (/^(true|false)$/i.test(raw)) return { set: true, value: raw.toLowerCase() === "true" };
  if (/^(none|null)$/i.test(raw)) return { set: true, value: null };
  if (/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(raw)) return { set: true, value: Number(raw) };
  if (/^[[{]/.test(raw)) {
    try {
      return { set: true, value: JSON.parse(raw) as Json };
    } catch {
      // not JSON: keep the text
    }
  }
  return { set: true, value: text };
}

/** A JSON value as an op argument (lists and dicts become list/dict values). */
export function toValue(value: Json): Value {
  if (Array.isArray(value)) return b.listOf(value.map(toValue));
  if (value !== null && typeof value === "object") {
    return b.dictOf(Object.entries(value).map(([k, v]) => [b.lit(k), toValue(v)]));
  }
  return b.lit(value);
}

export class MemberFormError extends Error {
  constructor(
    readonly key: string,
    readonly param: string,
  ) {
    super(key);
  }
}

export const displayName = (m: Member) => `${m.accessor.map((a) => `${a}.`).join("")}${m.name}`;

/** The op for a member and the form's raw values (only the parameters the user set). */
export function buildMemberOp(
  target: string,
  member: Member,
  values: Record<string, unknown>,
  columns: ColumnInfo[],
): OpJson {
  if (member.kind === "property") return b.attrOp(target, member.name, member.accessor);
  const kwargs: [string, Value][] = [];
  for (const p of member.params) {
    if (p.variadic) continue;
    const raw = values[p.name];
    let value: Value | undefined;
    switch (p.widget) {
      case "columns": {
        const picked = Array.isArray(raw) ? (raw as number[]) : [];
        const labels = picked.map((i) => columns[i]?.label as Json);
        if (labels.length === 1) value = b.colRef(labels[0]);
        else if (labels.length > 1) value = b.listOf(labels.map(b.colRef));
        break;
      }
      case "column":
        if (raw !== undefined && raw !== "") value = b.colRef(columns[Number(raw)]?.label as Json);
        break;
      case "frame":
        if (typeof raw === "string" && raw) value = b.nodeRef(raw);
        break;
      case "bool":
        if (raw === "true" || raw === "false") value = b.lit(raw === "true");
        break;
      case "choice":
      case "axis":
        if (typeof raw === "string" && raw !== "") value = toValue(JSON.parse(raw) as Json);
        break;
      case "int":
      case "float": {
        const text = String(raw ?? "").trim();
        if (text !== "") {
          const n = Number(text.replace(",", "."));
          if (!Number.isFinite(n) || (p.widget === "int" && !Number.isInteger(n))) {
            throw new MemberFormError("member.bad_number", p.name);
          }
          value = b.lit(n);
        }
        break;
      }
      case "func": {
        const text = String(raw ?? "").trim();
        if (text) value = text.startsWith("np.") ? b.fn(text.slice(3), "np") : b.fn(text);
        break;
      }
      default: {
        const parsed = parseLiteral(String(raw ?? ""));
        if (parsed.set) value = toValue(parsed.value as Json);
      }
    }
    if (value === undefined) {
      if (p.required) throw new MemberFormError("member.missing", p.name);
      continue;
    }
    kwargs.push([p.name, value]);
  }
  return b.callOp(target, member.name, kwargs, member.accessor);
}
