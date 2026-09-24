import type { Envelope } from "../generated/protocol";
import { decodeFrame, encodeFrame } from "./codec";
import { createEmitter } from "./emitter";
import type { Transport, TransportStatus } from "./types";

export function createWsTransport(url: string, maxDelayMs = 5000): Transport {
  const messages = createEmitter<[Envelope, DataView[]]>();
  const statuses = createEmitter<[TransportStatus]>();
  const queue: (string | ArrayBuffer)[] = [];
  let socket: WebSocket | null = null;
  let current: TransportStatus = "connecting";
  let closedByUser = false;
  let attempt = 0;

  const setStatus = (status: TransportStatus) => {
    current = status;
    statuses.emit(status);
  };

  const connect = () => {
    setStatus("connecting");
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    socket = ws;
    ws.onopen = () => {
      attempt = 0;
      setStatus("open");
      while (queue.length > 0) ws.send(queue.shift()!);
    };
    ws.onmessage = (event) => {
      const { env, buffers } = decodeFrame(event.data as string | ArrayBuffer);
      messages.emit(env, buffers);
    };
    ws.onclose = () => {
      socket = null;
      if (closedByUser) {
        setStatus("closed");
        return;
      }
      setStatus("connecting");
      const delay = Math.min(maxDelayMs, 250 * 2 ** attempt++);
      setTimeout(connect, delay);
    };
  };

  connect();

  return {
    kind: "ws",
    send(env, buffers = []) {
      const frame = encodeFrame(env, buffers);
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(frame);
      else queue.push(frame);
    },
    onMessage: messages.on,
    onStatus: statuses.on,
    status: () => current,
    close() {
      closedByUser = true;
      socket?.close();
      messages.clear();
    },
  };
}
