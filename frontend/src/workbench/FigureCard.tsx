import { Handle, type NodeProps, Position } from "@xyflow/react";
import { memo } from "react";
import { useTranslation } from "react-i18next";
import type { FigureInfo } from "../generated/protocol";

export type FigureCardData = { figure: FigureInfo };

function FigureCardImpl({ data, selected }: NodeProps & { data: FigureCardData }) {
  const { t } = useTranslation();
  const { figure } = data;
  const kinds = figure.kinds.map((k) => t(`plot.kind.${k}`)).join(", ");
  return (
    <div className="fl-card fl-figure-card" data-selected={selected ? "true" : "false"} data-testid="figure-card">
      <Handle type="target" position={Position.Left} className="fl-handle" />
      <div className="fl-card-icon" data-kind="Figure">
        ▟
      </div>
      <div className="fl-card-body">
        <div className="fl-card-name">{figure.name}</div>
        <div className="fl-card-meta">{figure.nlayers ? kinds : t("plot.empty_figure")}</div>
      </div>
    </div>
  );
}

export const FigureCard = memo(FigureCardImpl);
