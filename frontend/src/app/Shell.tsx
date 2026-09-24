import { useTranslation } from "react-i18next";
import { useAppStore } from "../state/context";
import { Loader } from "./Loader";

export function Shell() {
  const { t } = useTranslation();
  const connection = useAppStore((s) => s.connection);
  const error = useAppStore((s) => s.error);
  const snapshot = useAppStore((s) => s.snapshot);

  if (connection === "connecting") return <Loader label={t("app.connecting")} />;
  if (connection !== "ready" || !snapshot) {
    return (
      <div className="fl:flex fl:h-full fl:flex-col fl:items-center fl:justify-center fl:gap-2 fl:p-6">
        <p style={{ color: "var(--fl-danger)" }}>
          {connection === "mismatch" ? t("app.protocolMismatch") : t("app.error")}
        </p>
        {error ? (
          <pre className="fl:text-xs" style={{ color: "var(--fl-muted)" }}>
            {error}
          </pre>
        ) : null}
      </div>
    );
  }
  return (
    <main className="fl:flex fl:h-full fl:flex-col fl:gap-2 fl:p-4">
      <h2 className="fl:text-xs fl:uppercase fl:tracking-wide" style={{ color: "var(--fl-muted)" }}>
        {t("workbench.roots")}
      </h2>
      <ul className="fl:flex fl:flex-col fl:gap-1">
        {snapshot.roots.map((root) => (
          <li key={root.id} data-testid="root-item" className="fl:font-mono">
            {root.name} ·{" "}
            {root.shape.length === 2
              ? t("workbench.shape", { rows: root.shape[0], cols: root.shape[1] })
              : t("workbench.rows", { count: root.shape[0] })}
          </li>
        ))}
      </ul>
    </main>
  );
}
