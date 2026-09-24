import type { Envelope } from "../generated/protocol";

export type TransportStatus = "connecting" | "open" | "closed";

export interface Transport {
  readonly kind: "ws" | "anywidget";
  send(env: Envelope, buffers?: ArrayBuffer[]): void;
  onMessage(cb: (env: Envelope, buffers: DataView[]) => void): () => void;
  onStatus(cb: (status: TransportStatus) => void): () => void;
  status(): TransportStatus;
  close(): void;
}
