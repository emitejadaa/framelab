import { tableFromIPC } from "@uwdata/flechette";

export interface ColumnMeta {
  text: string | null;
  literal: string | null;
  dtype: string;
  strategy: string;
  fallback: string | null;
}

export interface WindowMeta {
  offset: number;
  nrows_total: number;
  ncols_total: number;
  col_start: number;
  columns: ColumnMeta[];
  index: ColumnMeta[];
}

export interface DecodedWindow {
  meta: WindowMeta;
  /** rows × index levels */
  index: (string | null)[][];
  /** rows × columns */
  cells: (string | null)[][];
}

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function formatDate(d: Date): string {
  const day = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  const h = d.getUTCHours();
  const m = d.getUTCMinutes();
  const s = d.getUTCSeconds();
  return h || m || s ? `${day} ${pad(h)}:${pad(m)}:${pad(s)}` : day;
}

/** Display text for one Arrow value, close to how pandas prints it. */
export function formatValue(v: unknown, dtype: string): string | null {
  if (v === null || v === undefined) return null;
  if (v instanceof Date) return formatDate(v);
  if (typeof v === "bigint") return v.toString();
  if (typeof v === "boolean") return v ? "True" : "False";
  if (typeof v === "number") {
    if (Number.isNaN(v)) return null;
    if (dtype.startsWith("float")) {
      if (Number.isInteger(v)) return `${v}.0`;
      return String(Number(v.toPrecision(10)));
    }
    return String(v);
  }
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, (_k, x) => (typeof x === "bigint" ? x.toString() : x));
  } catch {
    return String(v);
  }
}

export function decodeWindow(meta: WindowMeta, buffer: DataView): DecodedWindow {
  // Copy into a fresh ArrayBuffer: inside a WebSocket frame the Arrow bytes follow the JSON
  // header, so they are not 8-byte aligned and typed arrays (BigInt64Array…) would throw.
  const bytes = new Uint8Array(buffer.byteLength);
  bytes.set(new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength));
  const table = tableFromIPC(bytes, { useDate: true, useBigInt: true, useDecimalInt: true });
  const rows = table.numRows;
  const read = (name: string, dtype: string) => {
    const child = table.getChild(name);
    const out: (string | null)[] = [];
    for (let i = 0; i < rows; i++) out.push(formatValue(child.at(i), dtype));
    return out;
  };
  const indexCols = meta.index.map((m, k) => read(`i${k}`, m.dtype));
  const dataCols = meta.columns.map((m, j) => read(`c${meta.col_start + j}`, m.dtype));
  const index: (string | null)[][] = [];
  const cells: (string | null)[][] = [];
  for (let i = 0; i < rows; i++) {
    index.push(indexCols.map((col) => col[i]));
    cells.push(dataCols.map((col) => col[i]));
  }
  return { meta, index, cells };
}
