import type { TFunction } from "i18next";
import type { NodeInfo } from "../generated/protocol";

export const KIND_ICON: Record<string, string> = {
  DataFrame: "▦",
  Series: "≡",
  GroupBy: "⊞",
  Index: "⋮",
  Value: "#",
  Unknown: "·",
};

export function shapeText(node: Pick<NodeInfo, "shape">, t: TFunction): string {
  const shape = node.shape;
  if (!shape) return "—";
  if (shape.length === 2) return t("workbench.shape", { rows: shape[0], cols: shape[1] });
  return t("workbench.rows", { count: shape[0] });
}

export function bytesText(n: number | undefined): string {
  if (n === undefined) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export const isTabular = (kind: string) => kind === "DataFrame" || kind === "Series" || kind === "Index";
