import { useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import { bytesOf } from "./data";
import { usePortalContainer } from "../ui/portal";
import { NumberBox, Row, Select, Toggle } from "./controls";
import type { Catalog, FigureSpec } from "./types";

const MIME: Record<string, string> = {
  png: "image/png",
  svg: "image/svg+xml",
  pdf: "application/pdf",
  jpg: "image/jpeg",
};

/** Export: Python writes the file (its path goes into the code) or the browser downloads it. */
export function ExportDialog({
  figureId,
  spec,
  catalog,
  onClose,
}: {
  figureId: string;
  spec: FigureSpec;
  catalog: Catalog;
  onClose(): void;
}) {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const [format, setFormat] = useState("png");
  const [dpi, setDpi] = useState(spec.dpi);
  const [transparent, setTransparent] = useState(false);
  const [name, setName] = useState(`${spec.name}.png`);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const changeFormat = (next: string) => {
    setFormat(next);
    setName((n) => n.replace(/\.(png|svg|pdf|jpe?g)$/i, "") + `.${next}`);
  };

  const run = async (download: boolean) => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const params: Record<string, unknown> = { id: figureId, format, dpi, transparent, download };
      if (!download) params.path = name;
      const { result, buffers } = await rpc.request<{ path: string | null; bytes: number }>("figure.export", params);
      if (download && buffers[0]) {
        const url = URL.createObjectURL(new Blob([bytesOf(buffers[0])], { type: MIME[format] ?? "application/octet-stream" }));
        const a = document.createElement("a");
        a.href = url;
        a.download = name.split(/[\\/]/).pop() || `${spec.name}.${format}`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
        setDone(t("plot.export.downloaded"));
      } else {
        setDone(t("plot.export.saved", { path: result.path }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  if (!portal) return null;
  return createPortal(
    <div className="fl-overlay" onMouseDown={onClose}>
      <div className="fl-dialog" onMouseDown={(e) => e.stopPropagation()} onKeyDown={(e) => e.key === "Escape" && onClose()}>
        <div className="fl-dialog-title">{t("plot.export.title", { name: spec.name })}</div>
        <div className="fl-pair">
          <Row label={t("plot.export.format")}>
            <Select value={format} options={catalog.formats.map((f) => ({ value: f, label: f.toUpperCase() }))} onChange={changeFormat} />
          </Row>
          <Row label={t("plot.fig.dpi")} hint="dpi">
            <NumberBox value={dpi} integer min={30} max={1200} onCommit={(v) => v && setDpi(v)} />
          </Row>
        </div>
        <Toggle label={t("plot.export.transparent")} checked={transparent} onChange={setTransparent} />
        <Row label={t("plot.export.file")} hint={t("plot.export.file_hint")}>
          <input className="fl-input fl-mono" value={name} onChange={(e) => setName(e.target.value)} />
        </Row>
        {done ? <div className="fl-ok">{done}</div> : null}
        {error ? <div className="fl-form-error">{error}</div> : null}
        <div className="fl-dialog-actions">
          <button type="button" className="fl-btn" onClick={onClose}>
            {t("plot.export.close")}
          </button>
          <button type="button" className="fl-btn" disabled={busy} onClick={() => void run(true)}>
            {t("plot.export.download")}
          </button>
          <button type="button" className="fl-btn fl-btn-primary" disabled={busy || !name.trim()} onClick={() => void run(false)}>
            {t("plot.export.save")}
          </button>
        </div>
      </div>
    </div>,
    portal,
  );
}
