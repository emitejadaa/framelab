import { Handle, type NodeProps, Position } from "@xyflow/react";
import { memo } from "react";
import { useTranslation } from "react-i18next";
import type { NodeInfo } from "../generated/protocol";
import { KIND_ICON, shapeText } from "./format";

export type CardData = { info: NodeInfo };

function NodeCardImpl({ data, selected }: NodeProps & { data: CardData }) {
  const { t } = useTranslation();
  const { info } = data;
  const busy = info.state === "pending" || info.state === "computing";
  return (
    <div
      className="fl-card"
      data-state={info.state}
      data-selected={selected ? "true" : "false"}
      data-testid="node-card"
      title={info.error ? `${info.error.type}: ${info.error.message}` : info.name}
    >
      <Handle type="target" position={Position.Left} className="fl-handle" />
      <div className="fl-card-icon" data-kind={info.kind}>
        {KIND_ICON[info.kind] ?? "·"}
      </div>
      <div className="fl-card-body">
        <div className="fl-card-name">{info.name}</div>
        <div className="fl-card-meta">
          {busy ? <span className="fl-spin" /> : null}
          {info.state === "ready" ? shapeText(info, t) : t(`node.state.${info.state}`)}
        </div>
      </div>
      <Handle type="source" position={Position.Right} className="fl-handle" />
    </div>
  );
}

export const NodeCard = memo(NodeCardImpl);
