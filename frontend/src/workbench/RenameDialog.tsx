import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import { useAppStore } from "../state/context";
import { usePortalContainer } from "../ui/portal";

/** Rename a node: its variable in every piece of code; auto-named children follow. */
export function RenameDialog() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const nodeId = useAppStore((s) => s.renaming);
  const close = useAppStore((s) => s.askRename);
  const node = useAppStore((s) => s.snapshot?.nodes.find((n) => n.id === s.renaming) ?? null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setName(node?.name ?? "");
    setError(null);
  }, [nodeId]); // eslint-disable-line react-hooks/exhaustive-deps -- reset only when opening

  if (!nodeId || !node || !portal) return null;
  const submit = async () => {
    try {
      await rpc.request("node.rename", { id: nodeId, name });
      close(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };
  return createPortal(
    <div className="fl-overlay" onMouseDown={() => close(null)}>
      <form
        className="fl-dialog"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        onKeyDown={(e) => e.key === "Escape" && close(null)}
      >
        <div className="fl-dialog-title">{t("rename.title", { name: node.name })}</div>
        <input autoFocus className="fl-input fl-mono" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="fl-muted">{t("rename.help")}</div>
        {error ? <div className="fl-form-error">{error}</div> : null}
        <div className="fl-dialog-actions">
          <button type="button" className="fl-btn" onClick={() => close(null)}>
            {t("form.cancel")}
          </button>
          <button type="submit" className="fl-btn fl-btn-primary" disabled={!name.trim()}>
            {t("rename.confirm")}
          </button>
        </div>
      </form>
    </div>,
    portal,
  );
}
