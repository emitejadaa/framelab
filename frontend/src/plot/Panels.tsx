import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import type { NodeInfo } from "../generated/protocol";
import type { Json } from "../ops/build";
import {
  allFields,
  ColorBox,
  NumberBox,
  RefChecks,
  RefSelect,
  Row,
  Section,
  Select,
  Slider,
  TextBox,
  Toggle,
} from "./controls";
import { blankLayer, useFields } from "./data";
import type { AxesSpec, Catalog, FieldInfo, FigureSpec, KindInfo, LayerSpec, PropInfo, Ref } from "./types";

type T = ReturnType<typeof useTranslation>["t"];

// ---- figure ---------------------------------------------------------------------------------
export function FigurePanel({
  spec,
  catalog,
  edit,
}: {
  spec: FigureSpec;
  catalog: Catalog;
  edit(change: (d: FigureSpec) => void): void;
}) {
  const { t } = useTranslation();
  const grid = [1, 2, 3, 4].map((n) => ({ value: String(n), label: String(n) }));
  return (
    <div className="fl-panel">
      <Section title={t("plot.figure")}>
        <Row label={t("plot.fig.name")} hint={t("plot.fig.name_hint")}>
          <TextBox value={spec.name} mono onCommit={(v) => edit((d) => void (d.name = v))} />
        </Row>
        <Row label={t("plot.fig.suptitle")} hint="suptitle">
          <TextBox value={spec.suptitle} onCommit={(v) => edit((d) => void (d.suptitle = v))} />
        </Row>
        <Row label={t("plot.fig.style")} hint="plt.style">
          <Select
            value={spec.style}
            options={catalog.styles.map((s) => ({ value: s, label: s === "default" ? t("plot.fig.style_default") : s }))}
            onChange={(v) => edit((d) => void (d.style = v))}
          />
        </Row>
      </Section>
      <Section title={t("plot.fig.size")}>
        <div className="fl-pair">
          <Row label={t("plot.fig.width")} hint="in">
            <NumberBox value={spec.width} min={1} max={40} step={0.5} onCommit={(v) => v && edit((d) => void (d.width = v))} />
          </Row>
          <Row label={t("plot.fig.height")} hint="in">
            <NumberBox value={spec.height} min={1} max={40} step={0.5} onCommit={(v) => v && edit((d) => void (d.height = v))} />
          </Row>
        </div>
        <Row label={t("plot.fig.dpi")} hint="dpi">
          <NumberBox value={spec.dpi} integer min={30} max={600} onCommit={(v) => v && edit((d) => void (d.dpi = v))} />
        </Row>
      </Section>
      <Section title={t("plot.fig.grid")}>
        <div className="fl-pair">
          <Row label={t("plot.fig.rows")}>
            <Select value={String(spec.nrows)} options={grid} onChange={(v) => edit((d) => void (d.nrows = Number(v)))} />
          </Row>
          <Row label={t("plot.fig.cols")}>
            <Select value={String(spec.ncols)} options={grid} onChange={(v) => edit((d) => void (d.ncols = Number(v)))} />
          </Row>
        </div>
        <Toggle label={t("plot.fig.sharex")} checked={spec.sharex} onChange={(v) => edit((d) => void (d.sharex = v))} />
        <Toggle label={t("plot.fig.sharey")} checked={spec.sharey} onChange={(v) => edit((d) => void (d.sharey = v))} />
      </Section>
    </div>
  );
}

// ---- axes -----------------------------------------------------------------------------------
function AxisLabel({ value, onChange, t }: { value: string | null; onChange(v: string | null): void; t: T }) {
  const mode = value === null ? "auto" : value === "" ? "none" : "custom";
  return (
    <div className="fl-stack">
      <Select
        value={mode}
        options={[
          { value: "auto", label: t("plot.axes.label_auto") },
          { value: "none", label: t("plot.axes.label_none") },
          { value: "custom", label: t("plot.axes.label_custom") },
        ]}
        onChange={(m) => onChange(m === "auto" ? null : m === "none" ? "" : value || "…")}
      />
      {mode === "custom" ? <TextBox value={value ?? ""} onCommit={(v) => onChange(v)} /> : null}
    </div>
  );
}

export function AxesPanel({
  axes,
  index,
  catalog,
  change,
}: {
  axes: AxesSpec;
  index: number;
  catalog: Catalog;
  change(fn: (a: AxesSpec) => void): void;
}) {
  const { t } = useTranslation();
  const scales = catalog.scales.map((s) => ({ value: s, label: t(`plot.scale.${s}`) }));
  const limits = (which: "xlim" | "ylim") => (
    <div className="fl-pair">
      <NumberBox value={axes[which][0]} allowEmpty placeholder={t("plot.auto")} onCommit={(v) => change((a) => void (a[which][0] = v))} />
      <NumberBox value={axes[which][1]} allowEmpty placeholder={t("plot.auto")} onCommit={(v) => change((a) => void (a[which][1] = v))} />
    </div>
  );
  return (
    <div className="fl-panel">
      <Section title={t("plot.axes_n", { n: index + 1 })}>
        <Row label={t("plot.axes.title")} hint="set_title">
          <TextBox value={axes.title} onCommit={(v) => change((a) => void (a.title = v))} />
        </Row>
        <Row label={t("plot.axes.xlabel")} hint="set_xlabel">
          <AxisLabel t={t} value={axes.xlabel} onChange={(v) => change((a) => void (a.xlabel = v))} />
        </Row>
        <Row label={t("plot.axes.ylabel")} hint="set_ylabel">
          <AxisLabel t={t} value={axes.ylabel} onChange={(v) => change((a) => void (a.ylabel = v))} />
        </Row>
        <Row label={t("plot.axes.legend")} hint="legend">
          <Select
            value={axes.legend}
            options={[
              { value: "auto", label: t("plot.axes.legend_auto") },
              { value: "none", label: t("plot.axes.legend_none") },
              ...catalog.legend_locs.map((l) => ({ value: l, label: l })),
            ]}
            onChange={(v) => change((a) => void (a.legend = v))}
          />
        </Row>
      </Section>
      <Section title={t("plot.axes.scales")}>
        <div className="fl-pair">
          <Row label="X" hint="set_xscale">
            <Select value={axes.xscale} options={scales} onChange={(v) => change((a) => void (a.xscale = v))} />
          </Row>
          <Row label="Y" hint="set_yscale">
            <Select value={axes.yscale} options={scales} onChange={(v) => change((a) => void (a.yscale = v))} />
          </Row>
        </div>
        <Row label={t("plot.axes.xlim")} hint="set_xlim">
          {limits("xlim")}
        </Row>
        <Row label={t("plot.axes.ylim")} hint="set_ylim">
          {limits("ylim")}
        </Row>
        <Row label={t("plot.axes.xrotation")} hint="labelrotation">
          <Slider value={axes.xrotation} min={-90} max={90} step={15} onCommit={(v) => change((a) => void (a.xrotation = v))} />
        </Row>
        <Toggle label={t("plot.axes.grid")} checked={axes.grid} onChange={(v) => change((a) => void (a.grid = v))} />
      </Section>
    </div>
  );
}

// ---- layer ----------------------------------------------------------------------------------
function yLabel(kind: KindInfo, t: T): string {
  if (kind.y === "all") return t("plot.map.columns_all");
  if (["hist", "box", "violin", "pie"].includes(kind.key)) return t("plot.map.values");
  return kind.y === "many" ? t("plot.map.y_many") : t("plot.map.y");
}

function filterValueText(value: Json | undefined): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object" && !Array.isArray(value) && "iso" in value) return String(value.iso);
  return String(value);
}

function parseFilterValue(text: string, field: FieldInfo | undefined): Json {
  const raw = text.trim();
  if (field?.kind === "num" && raw !== "" && Number.isFinite(Number(raw))) return Number(raw);
  if (field?.kind === "bool" && /^(true|false)$/i.test(raw)) return raw.toLowerCase() === "true";
  if (field?.kind === "date" && /^\d{4}-\d{2}-\d{2}/.test(raw)) return { $: "ts", iso: raw, tz: null };
  return text;
}

function PropControl({
  prop,
  layer,
  change,
  t,
}: {
  prop: PropInfo;
  layer: LayerSpec;
  change(fn: (l: LayerSpec) => void): void;
  t: T;
}) {
  const set = prop.key in layer.props;
  const value = set ? layer.props[prop.key] : prop.default;
  const put = (v: Json) => change((l) => void (l.props[prop.key] = v));
  const reset = set ? () => change((l) => void delete l.props[prop.key]) : undefined;
  let control;
  switch (prop.type) {
    case "color":
      control = <ColorBox value={set ? String(value) : null} onChange={put} />;
      break;
    case "bool":
      control = <Toggle label={t("form.yes")} checked={Boolean(value)} onChange={put} />;
      break;
    case "choice":
      control = (
        <Select
          value={String(value)}
          options={(prop.choices ?? []).map((c) => ({ value: String(c), label: c === "" ? t("plot.none") : String(c) }))}
          onChange={put}
        />
      );
      break;
    case "int":
      control = <NumberBox value={Number(value)} integer min={prop.min} max={prop.max} onCommit={(v) => v !== null && put(v)} />;
      break;
    default:
      control =
        prop.min !== undefined && prop.max !== undefined && prop.max - prop.min <= 100 ? (
          <Slider value={Number(value)} min={prop.min} max={prop.max} step={prop.step ?? 0.1} onCommit={put} />
        ) : (
          <NumberBox value={Number(value)} min={prop.min} max={prop.max} onCommit={(v) => v !== null && put(v)} />
        );
  }
  return (
    <Row label={t(`plot.prop.${prop.key}`)} hint={prop.key} onReset={reset}>
      {control}
    </Row>
  );
}

function visibleProp(prop: PropInfo, layer: LayerSpec): boolean {
  if (layer.kind === "scatter") {
    if (prop.key === "cmap" || prop.key === "colorbar") return layer.color_by !== null;
    if (prop.key === "size_max") return layer.size_by !== null;
    if (prop.key === "s") return layer.size_by === null;
    if (prop.key === "color") return layer.color_by === null && layer.hue === null;
  }
  if (prop.key === "color" && (layer.hue !== null || layer.y.length > 1)) return false;
  return true;
}

export function LayerPanel({
  layer,
  catalog,
  sources,
  error,
  change,
  replace,
  remove,
}: {
  layer: LayerSpec;
  catalog: Catalog;
  sources: NodeInfo[];
  error: string | null;
  change(fn: (l: LayerSpec) => void): void;
  replace(l: LayerSpec): void;
  remove(): void;
}) {
  const { t } = useTranslation();
  const rpc = useRpc();
  const kind = catalog.kinds.find((k) => k.key === layer.kind) ?? catalog.kinds[0];
  const node = sources.find((n) => n.id === layer.source) ?? null;
  const fields = useFields(node?.id ?? null, node?.state ?? "");
  const series = Boolean(fields?.series);
  const columns = allFields(fields, false);
  const withIndex = allFields(fields, true);

  const guess = async (kindKey: string, source: string) => {
    const { result } = await rpc.request<Partial<LayerSpec>>("plot.default_layer", { id: source, kind: kindKey });
    return result;
  };
  const setKind = async (k: string) => {
    const info = catalog.kinds.find((c) => c.key === k);
    const needsX = info?.x === "column" && !layer.x;
    const needsY = info?.y !== "all" && layer.y.length === 0;
    if (!needsX && !needsY) return change((l) => void (l.kind = k));
    const first = await guess(k, layer.source);
    replace(blankLayer({ ...first, x: layer.x ?? first.x, y: layer.y.length ? layer.y : first.y, label: layer.label }));
  };
  const setSource = async (id: string) => {
    replace(blankLayer({ ...(await guess(layer.kind, id)), props: layer.props, label: layer.label }));
  };
  const rows = layer.rows;
  const filterField = columns.find((f) => JSON.stringify(f.ref) === JSON.stringify(rows.column ?? null));

  return (
    <div className="fl-panel" data-testid="layer-panel">
      {error ? <div className="fl-form-error fl-layer-error">{error}</div> : null}
      <Section title={t("plot.layer")}>
        <Row label={t("plot.kind_label")}>
          <Select
            value={layer.kind}
            testId="layer-kind"
            options={catalog.kinds.map((k) => ({ value: k.key, label: t(`plot.kind.${k.key}`) }))}
            onChange={(k) => void setKind(k)}
          />
        </Row>
        <Row label={t("plot.data")}>
          <Select value={layer.source} options={sources.map((n) => ({ value: n.id, label: n.name }))} onChange={(id) => void setSource(id)} />
        </Row>
      </Section>
      <Section title={t("plot.mapping")}>
        {kind.x !== "none" ? (
          <Row label={kind.x === "labels" ? t("plot.map.labels") : t("plot.map.x")} hint="x">
            <RefSelect
              fields={withIndex}
              testId="map-x"
              value={layer.x ?? (kind.x === "column" ? null : ({ index: true } as Ref))}
              none={kind.x === "column" ? t("plot.choose") : undefined}
              onChange={(v) => change((l) => void (l.x = v && "index" in v ? null : v))}
            />
          </Row>
        ) : null}
        {!series || kind.y === "all" ? (
          <Row label={yLabel(kind, t)} hint={kind.y === "one" ? "y" : undefined}>
            {kind.y === "one" || (layer.hue !== null && kind.y !== "all") ? (
              <RefSelect
                fields={columns}
                testId="map-y"
                value={layer.y[0] ?? null}
                none={t("plot.choose")}
                onChange={(v) => change((l) => void (l.y = v ? [v] : []))}
              />
            ) : (
              <RefChecks fields={columns} value={layer.y} onChange={(v) => change((l) => void (l.y = v))} />
            )}
          </Row>
        ) : null}
        {kind.hue && !series ? (
          <Row label={t("plot.map.hue")} hint="groupby">
            <RefSelect fields={columns} testId="map-hue" value={layer.hue} none={t("plot.none")} onChange={(v) => change((l) => void (l.hue = v))} />
          </Row>
        ) : null}
        {kind.color_by && !series ? (
          <Row label={t("plot.map.color_by")} hint="c">
            <RefSelect fields={columns} value={layer.color_by} none={t("plot.none")} onChange={(v) => change((l) => void (l.color_by = v))} />
          </Row>
        ) : null}
        {kind.size_by && !series ? (
          <Row label={t("plot.map.size_by")} hint="s">
            <RefSelect fields={columns} value={layer.size_by} none={t("plot.none")} onChange={(v) => change((l) => void (l.size_by = v))} />
          </Row>
        ) : null}
      </Section>
      <Section title={t("plot.rows.title")}>
        <Row label={t("plot.rows.which")}>
          <Select
            value={rows.mode}
            options={(["all", "head", "tail", "sample", "filter"] as const).map((m) => ({ value: m, label: t(`plot.rows.${m}`) }))}
            onChange={(m) =>
              change((l) => {
                l.rows = m === "filter" ? { mode: m, column: columns[0]?.ref ?? null, op: "notna" } : { mode: m, n: rows.n ?? 100 };
              })
            }
          />
        </Row>
        {rows.mode === "head" || rows.mode === "tail" || rows.mode === "sample" ? (
          <Row label={t("plot.rows.n")} hint="n">
            <NumberBox value={rows.n ?? 100} integer min={1} onCommit={(v) => v && change((l) => void (l.rows.n = v))} />
          </Row>
        ) : null}
        {rows.mode === "filter" ? (
          <>
            <Row label={t("plot.rows.column")}>
              <RefSelect fields={columns} value={rows.column ?? null} onChange={(v) => change((l) => void (l.rows.column = v))} />
            </Row>
            <div className="fl-pair">
              <Select
                value={rows.op ?? "=="}
                options={catalog.filter_ops.map((o) => ({ value: o, label: t(`plot.op.${o}`, { defaultValue: o }) }))}
                onChange={(o) =>
                  change((l) => {
                    l.rows.op = o;
                    if (o !== "isna" && o !== "notna" && (l.rows.value === undefined || l.rows.value === null)) l.rows.value = "";
                  })
                }
              />
              {rows.op === "isna" || rows.op === "notna" ? null : (
                <TextBox
                  value={filterValueText(rows.value)}
                  placeholder={filterField?.kind === "date" ? "2024-01-31" : ""}
                  onCommit={(v) => change((l) => void (l.rows.value = parseFilterValue(v, filterField)))}
                />
              )}
            </div>
          </>
        ) : null}
      </Section>
      {!["pie", "box", "violin", "heatmap", "hexbin"].includes(layer.kind) ? (
        <Section title={t("plot.legend")}>
          <Row label={t("plot.label")} hint="label">
            <TextBox value={layer.label} placeholder={t("plot.auto")} onCommit={(v) => change((l) => void (l.label = v))} />
          </Row>
        </Section>
      ) : null}
      <Section title={t("plot.style")}>
        {kind.props
          .filter((p) => visibleProp(p, layer))
          .map((p) => (
            <PropControl key={p.key} prop={p} layer={layer} change={change} t={t} />
          ))}
      </Section>
      <button type="button" className="fl-btn fl-btn-quiet-danger" onClick={remove}>
        {t("plot.remove_layer")}
      </button>
    </div>
  );
}
