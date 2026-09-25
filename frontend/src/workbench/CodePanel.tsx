import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import { useAppStore } from "../state/context";
import { copyText } from "../ui/clipboard";

export function CodePanel() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const node = useAppStore((s) => s.snapshot?.nodes.find((n) => n.id === s.selectedId) ?? null);
  const [mode, setMode] = useState<"origin" | "step">("origin");
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);
  const nodes = useAppStore((s) => s.snapshot?.nodes);
  const download = async (format: "py" | "ipynb") => {
    const { result } = await rpc.request<{ text: string }>("session.export", { format });
    const type = format === "py" ? "text/x-python" : "application/x-ipynb+json";
    const url = URL.createObjectURL(new Blob([result.text], { type }));
    const a = document.createElement("a");
    a.href = url;
    const roots = (nodes ?? []).filter((n) => n.parents.length === 0).map((n) => n.name);
    a.download = `${roots.join("_") || "framelab"}.${format}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };

  useEffect(() => {
    if (!node) return;
    let alive = true;
    rpc
      .request<{ code: string }>("node.code", { id: node.id, mode })
      .then(({ result }) => alive && setCode(result.code))
      .catch(() => alive && setCode(""));
    return () => {
      alive = false;
    };
  }, [node?.id, node?.state, mode, rpc, node]);

  return (
    <section className="fl-codepanel">
      <div className="fl-toolbar">
        <span className="fl-section-inline">{t("code.title")}</span>
        <div className="fl-segmented">
          {(["origin", "step"] as const).map((m) => (
            <button key={m} type="button" data-active={mode === m ? "true" : "false"} onClick={() => setMode(m)}>
              {t(`code.${m}`)}
            </button>
          ))}
        </div>
        <span className="fl-spacer" />
        <span className="fl-muted fl-hint-inline">{t("code.export_title")}</span>
        {(["py", "ipynb"] as const).map((format) => (
          <button key={format} type="button" className="fl-btn" onClick={() => void download(format)}>
            ↓ .{format}
          </button>
        ))}
        <button
          type="button"
          className="fl-btn"
          disabled={!code}
          onClick={async () => {
            if (await copyText(code)) {
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            }
          }}
        >
          {copied ? t("code.copied") : t("code.copy")}
        </button>
      </div>
      <pre className="fl-code fl-code-main" data-testid="code">
        {code}
      </pre>
    </section>
  );
}
