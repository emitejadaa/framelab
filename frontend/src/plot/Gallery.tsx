import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import type { NodeInfo } from "../generated/protocol";
import { fieldLabel } from "./controls";
import { useFields, useSuggestions } from "./data";
import { KindIcon } from "./icons";
import { type Catalog, type LayerSpec, type Ref, refKey } from "./types";

const FAMILIES = ["lines", "bars", "distribution", "points", "parts", "matrix"];

/** Pick what to draw: suggestions for this data first, then every chart type by family. */
export function Gallery({
  catalog,
  sources,
  source,
  onSource,
  onPick,
}: {
  catalog: Catalog;
  sources: NodeInfo[];
  source: string | null;
  onSource(id: string): void;
  onPick(layer: Partial<LayerSpec>): void;
}) {
  const { t } = useTranslation();
  const rpc = useRpc();
  const node = sources.find((n) => n.id === source) ?? null;
  const fields = useFields(node?.id ?? null, node?.state ?? "");
  const suggestions = useSuggestions(node?.id ?? null, node?.state ?? "");
  const [problem, setProblem] = useState<string | null>(null);

  const name = (ref: Ref | null | undefined) => {
    if (!ref || !fields) return "";
    const all = [...(fields.index ? [fields.index] : []), ...fields.fields];
    const f = all.find((g) => refKey(g.ref) === refKey(ref));
    return f ? fieldLabel(f, t) : "?";
  };
  const describe = (layer: Partial<LayerSpec>) => {
    const ys = (layer.y ?? []).map(name).join(", ");
    const parts = [ys || (layer.kind === "heatmap" ? t("plot.all_columns") : "")];
    if (layer.x) parts.push(t("plot.by_x", { x: name(layer.x) }));
    if (layer.hue) parts.push(t("plot.split_by", { col: name(layer.hue) }));
    return parts.filter(Boolean).join(" · ");
  };

  const pick = async (kind: string) => {
    if (!node) return;
    try {
      const { result } = await rpc.request<Partial<LayerSpec>>("plot.default_layer", { id: node.id, kind });
      onPick(result);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="fl-gallery" data-testid="gallery">
      <div className="fl-gallery-source">
        <span className="fl-muted">{t("plot.data")}</span>
        <select className="fl-input" value={source ?? ""} onChange={(e) => onSource(e.target.value)}>
          {!source ? <option value="">{t("plot.choose_data")}</option> : null}
          {sources.map((n) => (
            <option key={n.id} value={n.id}>
              {n.name}
            </option>
          ))}
        </select>
      </div>
      {suggestions.length ? (
        <>
          <div className="fl-psection-title">{t("plot.suggested")}</div>
          <div className="fl-suggestions">
            {suggestions.map((s, i) => (
              <button key={`${s.kind}-${i}`} type="button" className="fl-suggestion" onClick={() => onPick(s)}>
                <KindIcon kind={s.kind ?? "line"} />
                <span>
                  <strong>{t(`plot.kind.${s.kind}`)}</strong>
                  <span className="fl-muted">{describe(s)}</span>
                </span>
              </button>
            ))}
          </div>
        </>
      ) : null}
      {FAMILIES.map((family) => {
        const kinds = catalog.kinds.filter((k) => k.family === family);
        if (!kinds.length) return null;
        return (
          <div key={family}>
            <div className="fl-psection-title">{t(`plot.family.${family}`)}</div>
            <div className="fl-kinds">
              {kinds.map((k) => (
                <button
                  key={k.key}
                  type="button"
                  className="fl-kind"
                  data-testid={`kind-${k.key}`}
                  disabled={!node || node.state !== "ready"}
                  title={t(`plot.kind_help.${k.key}`)}
                  onClick={() => void pick(k.key)}
                >
                  <KindIcon kind={k.key} />
                  <span>{t(`plot.kind.${k.key}`)}</span>
                </button>
              ))}
            </div>
          </div>
        );
      })}
      {problem ? <div className="fl-form-error">{problem}</div> : null}
    </div>
  );
}
