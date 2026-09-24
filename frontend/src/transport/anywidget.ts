import type { AnyModel } from "@anywidget/types";
import type { Envelope } from "../generated/protocol";
import { createEmitter } from "./emitter";
import type { Transport, TransportStatus } from "./types";

export function createAnyWidgetTransport(model: AnyModel): Transport {
  const messages = createEmitter<[Envelope, DataView[]]>();
  const statuses = createEmitter<[TransportStatus]>();
  const handler = (msg: unknown, buffers: DataView[]) => messages.emit(msg as Envelope, buffers ?? []);
  model.on("msg:custom", handler);
  return {
    kind: "anywidget",
    send(env, buffers = []) {
      model.send(env, undefined, buffers);
    },
    onMessage: messages.on,
    onStatus: statuses.on,
    status: () => "open",
    close() {
      model.off("msg:custom", handler);
      messages.clear();
      statuses.clear();
    },
  };
}
