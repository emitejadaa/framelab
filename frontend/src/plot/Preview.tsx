import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import { bytesOf } from "./data";
import { copyText } from "../ui/clipboard";
import type { RenderMeta } from "./types";

const message = (err: unknown) => (err instanceof Error ? err.message : String(err));

/** The figure as matplotlib draws it; the last image stays (dimmed) while the next one renders. */
export function Preview({
  figureId,
  version,
  inputs,
  onMeta,
}: {
  figureId: string;
  version: number;
  /** changes when a source's data changes (e.g. a node finished computing) */
  inputs: string;
  onMeta(meta: RenderMeta | null): void;
}) {
  const { t } = useTranslation();
  const rpc = useRpc();
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [image, setImage] = useState<{ url: string; w: number; h: number; sampled: boolean } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const meta = useRef(onMeta);
  meta.current = onMeta;
  const url = useRef<string | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const observer = new ResizeObserver(([entry]) => {
      clearTimeout(timer);
      const { width, height } = entry.contentRect;
      timer = setTimeout(() => setSize({ w: Math.floor(width), h: Math.floor(height) }), 120);
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!size || size.w < 40 || size.h < 40) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let alive = true;
    setLoading(true);
    const timer = setTimeout(() => {
      rpc
        .request<RenderMeta>("figure.render", { id: figureId, width_px: size.w - 16, height_px: size.h - 16, dpr })
        .then(({ result, buffers }) => {
          if (!alive) return;
          if (url.current) URL.revokeObjectURL(url.current);
          url.current = URL.createObjectURL(new Blob([bytesOf(buffers[0])], { type: "image/png" }));
          setImage({ url: url.current, w: result.width / dpr, h: result.height / dpr, sampled: result.sampled });
          setError(null);
          meta.current(result);
        })
        .catch((err) => alive && setError(message(err)))
        .finally(() => alive && setLoading(false));
    }, 60);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [rpc, figureId, version, inputs, size]);

  useEffect(() => () => void (url.current && URL.revokeObjectURL(url.current)), []);

  return (
    <div ref={box} className="fl-preview" data-loading={loading ? "true" : "false"}>
      {image ? (
        <img
          src={image.url}
          width={image.w}
          height={image.h}
          alt={t("plot.preview_alt")}
          data-testid="plot-image"
          draggable={false}
        />
      ) : (
        <div className="fl-muted">{t("app.loading")}</div>
      )}
      {loading ? <span className="fl-spin fl-preview-spin" /> : null}
      {image?.sampled ? <span className="fl-preview-badge">{t("plot.sampled")}</span> : null}
      {error ? <div className="fl-form-error fl-preview-error">{error}</div> : null}
    </div>
  );
}

/** The figure's code: everything from the data (default) or just the figure. */
export function FigureCode({ figureId, version }: { figureId: string; version: string }) {
  const { t } = useTranslation();
  const rpc = useRpc();
  const [mode, setMode] = useState<"full" | "figure">("full");
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    let alive = true;
    rpc
      .request<{ code: string }>("figure.code", { id: figureId, mode })
      .then(({ result }) => alive && setCode(result.code))
      .catch((err) => alive && setCode(`# ${message(err)}`));
    return () => {
      alive = false;
    };
  }, [rpc, figureId, version, mode]);
  return (
    <div className="fl-codepanel fl-plot-code">
      <div className="fl-toolbar">
        <span className="fl-section-inline">{t("code.title")}</span>
        <div className="fl-segmented">
          <button type="button" data-active={mode === "full" ? "true" : "false"} onClick={() => setMode("full")}>
            {t("plot.code_full")}
          </button>
          <button type="button" data-active={mode === "figure" ? "true" : "false"} onClick={() => setMode("figure")}>
            {t("plot.code_figure")}
          </button>
        </div>
        <span className="fl-spacer" />
        <button
          type="button"
          className="fl-btn"
          data-testid="copy-figure-code"
          onClick={() =>
            void copyText(code).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            })
          }
        >
          {copied ? t("code.copied") : t("code.copy")}
        </button>
      </div>
      <pre className="fl-code fl-code-main" data-testid="figure-code">
        {code}
      </pre>
    </div>
  );
}
