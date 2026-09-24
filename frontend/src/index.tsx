import "./styles/index.css";
import type { AnyModel } from "@anywidget/types";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { createAnyWidgetTransport } from "./transport/anywidget";
import type { Transport } from "./transport/types";
import { createWsTransport } from "./transport/ws";

export function mount(el: HTMLElement, transport: Transport): () => void {
  const root = createRoot(el);
  root.render(<App transport={transport} />);
  return () => {
    root.unmount();
    transport.close();
  };
}

export function mountWs(el: HTMLElement, wsUrl: string): () => void {
  return mount(el, createWsTransport(wsUrl));
}

/** anywidget front-end module (AFM) entry point. */
export default {
  render({ model, el }: { model: AnyModel; el: HTMLElement }) {
    el.style.height = `${(model.get("height") as number | undefined) ?? 720}px`;
    el.style.position = "relative";
    return mount(el, createAnyWidgetTransport(model));
  },
};
