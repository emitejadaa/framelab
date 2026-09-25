import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import { useAppStore } from "../state/context";
import { usePortalContainer } from "../ui/portal";

interface Preview {
  ids: string[];
  names: string[];
  figures: string[];
}

/** Confirm before deleting a node and everything computed from it. */
export function DeleteDialog() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const nodeId = useAppStore((s) => s.deleting);
  const close = useAppStore((s) => s.askDelete);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setPreview(null);
    setError(null);
    if (!nodeId) return;
    let alive = true;
    rpc
      .request<Preview>("node.delete_preview", { id: nodeId })
      .then(({ result }) => alive && setPreview(result))
      .catch((err) => alive && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      alive = false;
    };
  }, [nodeId, rpc]);

  if (!nodeId || !portal) return null;
  const confirm = async () => {
    setBusy(true);
    try {
      await rpc.request("node.delete", { id: nodeId });
      close(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  const extra = preview ? preview.names.length - 1 : 0;
  return createPortal(
    <div className="fl-overlay" onMouseDown={() => close(null)}>
      <div
        className="fl-dialog"
        role="alertdialog"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") close(null);
          if (e.key === "Enter" && preview) void confirm();
        }}
      >
        <div className="fl-dialog-title">{t("delete.title", { name: preview?.names[0] ?? "…" })}</div>
        {preview ? (
          <>
            <p>{extra ? t("delete.with_children", { count: extra }) : t("delete.alone")}</p>
            {extra ? <div className="fl-delete-list">{preview.names.slice(1).join(", ")}</div> : null}
            {preview.figures.length ? (
              <p className="fl-warn-text">{t("delete.figures", { names: preview.figures.join(", ") })}</p>
            ) : null}
          </>
        ) : null}
        {error ? <div className="fl-form-error">{error}</div> : null}
        <div className="fl-dialog-actions">
          <button type="button" className="fl-btn" onClick={() => close(null)}>
            {t("form.cancel")}
          </button>
          <button
            type="button"
            className="fl-btn fl-btn-danger"
            autoFocus
            disabled={!preview || busy}
            onClick={() => void confirm()}
          >
            {t("delete.confirm")}
          </button>
        </div>
      </div>
    </div>,
    portal,
  );
}
