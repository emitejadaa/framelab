import type { Envelope } from "../generated/protocol";

// Binary frames mirror framelab/protocol/codec.py:
// uint32 big-endian header length N · N bytes of UTF-8 JSON envelope · raw buffers.
const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function encodeFrame(env: Envelope, buffers: ArrayBuffer[] = []): string | ArrayBuffer {
  if (buffers.length === 0) return JSON.stringify(env);
  const header = encoder.encode(JSON.stringify({ ...env, buffers: buffers.map((b) => b.byteLength) }));
  const total = 4 + header.byteLength + buffers.reduce((n, b) => n + b.byteLength, 0);
  const out = new Uint8Array(total);
  new DataView(out.buffer).setUint32(0, header.byteLength, false);
  out.set(header, 4);
  let offset = 4 + header.byteLength;
  for (const b of buffers) {
    out.set(new Uint8Array(b), offset);
    offset += b.byteLength;
  }
  return out.buffer;
}

export function decodeFrame(data: string | ArrayBuffer): { env: Envelope; buffers: DataView[] } {
  if (typeof data === "string") return { env: JSON.parse(data) as Envelope, buffers: [] };
  const view = new DataView(data);
  const n = view.getUint32(0, false);
  const env = JSON.parse(decoder.decode(new Uint8Array(data, 4, n))) as Envelope;
  const buffers: DataView[] = [];
  let offset = 4 + n;
  for (const length of env.buffers ?? []) {
    buffers.push(new DataView(data, offset, length));
    offset += length;
  }
  return { env, buffers };
}
