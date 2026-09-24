import { type PointerEvent, useEffect, useMemo, useState } from "react";
import { I18nextProvider } from "react-i18next";
import { useStore } from "zustand";
import { type HelloResult, PROTOCOL_VERSION, type SessionSnapshot } from "../generated/protocol";
import { createI18n, pickLanguage } from "../i18n";
import { StoreProvider } from "../state/context";
import { createAppStore } from "../state/store";
import { createRpc, RpcError } from "../transport/rpc";
import type { Transport } from "../transport/types";
import { PortalProvider } from "../ui/portal";
import { Shell } from "./Shell";

function optionValue(snapshot: SessionSnapshot | null, key: string): unknown {
  return snapshot?.options.find((o) => o.key === key)?.value;
}

const INTERACTIVE = "input, textarea, select, button, a[href], [contenteditable], [tabindex]:not(.fl-root)";

/**
 * Keep keyboard focus inside the app so host shortcuts stay quiet: JupyterLab ignores
 * key events whose target is inside [data-lm-suppress-shortcuts], but only if focus
 * actually moved into the widget (it stays on the notebook cell otherwise).
 */
function focusRoot(event: PointerEvent<HTMLDivElement>) {
  const target = event.target as HTMLElement;
  if (!target.closest(INTERACTIVE)) event.currentTarget.focus({ preventScroll: true });
}

function browserLanguages(): readonly string[] {
  return navigator.languages?.length ? navigator.languages : [navigator.language];
}

export function App({ transport }: { transport: Transport }) {
  const [store] = useState(createAppStore);
  const [rpc] = useState(() => createRpc(transport));
  const [portalEl, setPortalEl] = useState<HTMLDivElement | null>(null);
  const snapshot = useStore(store, (s) => s.snapshot);
  const lang = pickLanguage(optionValue(snapshot, "general.language"), browserLanguages());
  const [initialLang] = useState(lang);
  const i18n = useMemo(() => createI18n(initialLang), [initialLang]);

  useEffect(() => {
    void i18n.changeLanguage(lang);
  }, [i18n, lang]);

  useEffect(() => {
    const state = store.getState();
    const handshake = async () => {
      state.setConnection("connecting");
      try {
        const hello = await rpc.request<HelloResult>("session.hello", {
          protocol_version: PROTOCOL_VERSION,
          client: transport.kind,
        });
        state.setHello(hello.result);
        const snap = await rpc.request<SessionSnapshot>("session.snapshot");
        state.setSnapshot(snap.result);
        state.setConnection("ready");
      } catch (err) {
        if (err instanceof RpcError && err.code === "protocol_mismatch") {
          state.setConnection("mismatch", err.message);
        } else {
          state.setConnection("error", err instanceof Error ? err.message : String(err));
        }
      }
    };
    const offStatus = transport.onStatus((status) => {
      if (status === "open") void handshake();
      else if (status === "connecting") state.setConnection("connecting");
    });
    if (transport.status() === "open") void handshake();
    return () => {
      offStatus();
      rpc.dispose();
    };
  }, [rpc, store, transport]);

  const theme = (optionValue(snapshot, "general.theme") as string | undefined) ?? "system";
  const reduceMotion = optionValue(snapshot, "general.reduce_motion") === true;

  return (
    <StoreProvider value={store}>
      <I18nextProvider i18n={i18n}>
        <PortalProvider value={portalEl}>
          <div
            className="fl-root"
            tabIndex={-1}
            onPointerDown={focusRoot}
            data-theme={theme}
            data-reduce-motion={reduceMotion ? "true" : "false"}
            data-lm-suppress-shortcuts="true"
            data-jp-suppress-context-menu="true"
          >
            <Shell />
            <div ref={setPortalEl} className="fl-portal" />
          </div>
        </PortalProvider>
      </I18nextProvider>
    </StoreProvider>
  );
}
