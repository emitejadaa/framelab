/** The figure spec as Python normalizes it (framelab/plot/spec.py is the source of truth). */
import type { Json } from "../ops/build";

export type Ref = { col: Json } | { index: true } | { values: true };

export interface Rows {
  mode: "all" | "head" | "tail" | "sample" | "filter";
  n?: number;
  column?: Ref | null;
  op?: string;
  value?: Json;
}

export interface LayerSpec {
  kind: string;
  source: string;
  x: Ref | null;
  y: Ref[];
  hue: Ref | null;
  color_by: Ref | null;
  size_by: Ref | null;
  rows: Rows;
  props: Record<string, Json>;
  label: string;
}

export interface AxesSpec {
  title: string;
  xlabel: string | null;
  ylabel: string | null;
  xscale: string;
  yscale: string;
  xlim: [number | null, number | null];
  ylim: [number | null, number | null];
  grid: boolean;
  legend: string;
  xrotation: number;
  layers: LayerSpec[];
}

export interface FigureSpec {
  version: number;
  name: string;
  width: number;
  height: number;
  dpi: number;
  style: string;
  suptitle: string;
  nrows: number;
  ncols: number;
  sharex: boolean;
  sharey: boolean;
  axes: AxesSpec[];
}

export interface FigureState {
  id: string;
  version: number;
  spec: FigureSpec;
  can_undo: boolean;
  can_redo: boolean;
  exported: { path: string; dpi: number; transparent: boolean; format: string } | null;
  origin: string | null;
}

export interface PropInfo {
  key: string;
  type: "color" | "float" | "int" | "bool" | "choice";
  default: Json;
  min?: number;
  max?: number;
  step?: number;
  choices?: Json[];
}

export interface KindInfo {
  key: string;
  family: string;
  method: string;
  x: "index" | "column" | "labels" | "none";
  y: "one" | "many" | "all";
  hue: boolean;
  color_by: boolean;
  size_by: boolean;
  props: PropInfo[];
}

export interface Catalog {
  kinds: KindInfo[];
  styles: string[];
  colormaps: string[];
  legend_locs: string[];
  scales: string[];
  filter_ops: string[];
  formats: string[];
}

export interface FieldInfo {
  ref: Ref;
  text: string;
  dtype: string;
  kind: "num" | "date" | "cat" | "bool" | "other";
  distinct: number | null;
}

export interface SourceFields {
  id: string;
  tabular: boolean;
  rows: number;
  series?: boolean;
  index: FieldInfo | null;
  fields: FieldInfo[];
}

export interface RenderMeta {
  id: string;
  version: number;
  width: number;
  height: number;
  sampled: boolean;
  errors: { axes: number; layer: number; message: string }[];
  warnings: string[];
}

export type Selection =
  | { type: "figure" }
  | { type: "axes"; axes: number }
  | { type: "layer"; axes: number; layer: number }
  | { type: "gallery"; axes: number };

export const refKey = (ref: Ref | null | undefined): string => (ref ? JSON.stringify(ref) : "");
export const sameRef = (a: Ref | null | undefined, b: Ref | null | undefined) => refKey(a) === refKey(b);
