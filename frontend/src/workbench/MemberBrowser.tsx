import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useRpc } from "../data/rpcContext";
import { useAppStore } from "../state/context";
import { usePortalContainer } from "../ui/portal";
import { applyOp } from "./applyOp";
import { buildMemberOp, displayName, type Member, useMembers } from "./members";

/** Every pandas method and attribute of a node, by API reference category, searchable. */
export function MemberBrowser() {
  const { t } = useTranslation();
  const rpc = useRpc();
  const portal = usePortalContainer();
  const nodeId = useAppStore((s) => s.browser);
  const close = useAppStore((s) => s.openBrowser);
  const openMemberForm = useAppStore((s) => s.openMemberForm);
  const select = useAppStore((s) => s.select);
  const node = useAppStore((s) => s.snapshot?.nodes.find((n) => n.id === s.browser) ?? null);
  const { members, loading } = useMembers(nodeId, node?.state ?? "");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of members) counts.set(m.category, (counts.get(m.category) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [members]);

  const q = query.trim().toLowerCase();
  const shown = members
    .filter((m) => !category || m.category === category)
    .filter((m) => !q || displayName(m).toLowerCase().includes(q) || m.summary.toLowerCase().includes(q))
    .sort((a, b) => {
      if (q) {
        const aStarts = a.name.toLowerCase().startsWith(q) ? 0 : 1;
        const bStarts = b.name.toLowerCase().startsWith(q) ? 0 : 1;
        if (aStarts !== bStarts) return aStarts - bStarts;
      }
      return displayName(a).localeCompare(displayName(b));
    });

  if (!nodeId || !node || !portal) return null;

  const pick = async (member: Member) => {
    if (member.kind === "method") {
      openMemberForm({ nodeId, member });
      return;
    }
    try {
      const created = await applyOp(rpc, buildMemberOp(nodeId, member, {}, []));
      select(created.id);
      close(null);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    }
  };

  return createPortal(
    <div className="fl-overlay" onMouseDown={() => close(null)}>
      <div
        className="fl-dialog fl-browser"
        data-testid="member-browser"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && close(null)}
      >
        <div className="fl-dialog-title">{t("browser.title", { name: node.name })}</div>
        <input
          autoFocus
          className="fl-input"
          placeholder={t("browser.search")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && shown[0]) void pick(shown[0]);
          }}
        />
        <div className="fl-browser-body">
          <nav className="fl-browser-cats">
            <button type="button" data-active={category === null ? "true" : "false"} onClick={() => setCategory(null)}>
              {t("browser.all")} <span className="fl-muted">{members.length}</span>
            </button>
            {categories.map(([name, count]) => (
              <button key={name} type="button" data-active={category === name ? "true" : "false"} onClick={() => setCategory(name)}>
                {name} <span className="fl-muted">{count}</span>
              </button>
            ))}
          </nav>
          <div className="fl-browser-list">
            {loading ? <div className="fl-muted">{t("app.loading")}</div> : null}
            {!loading && shown.length === 0 ? <div className="fl-muted">{t("browser.empty")}</div> : null}
            {shown.map((m) => (
              <button
                key={`${m.accessor.join(".")}:${m.name}`}
                type="button"
                className="fl-browser-item"
                data-testid={`member-${displayName(m)}`}
                onClick={() => void pick(m)}
              >
                <span className="fl-mono">
                  {displayName(m)}
                  {m.kind === "method" ? "()" : ""}
                </span>
                <span className="fl-browser-summary">{m.summary}</span>
                {m.returns !== "unknown" ? <span className="fl-badge fl-badge-muted">{m.returns}</span> : null}
              </button>
            ))}
          </div>
        </div>
        {problem ? <div className="fl-form-error">{problem}</div> : null}
      </div>
    </div>,
    portal,
  );
}
