/**
 * Video WebSocket (§5.4). Binary frames: "HSF1" | u16 BE header_len | header JSON | JPEG bytes.
 * One socket per tab; camera tiles register watchers and the hub keeps the server subscription
 * equal to the union of watched cameras (latest frame wins, nothing is queued here either).
 */
import type { FrameHeader } from "../api/types";
import { backoffMs, browserSocket, type SocketFactory, type SocketLike } from "./control";

const MAGIC = [0x48, 0x53, 0x46, 0x31]; // "HSF1"

export interface Frame {
  header: FrameHeader;
  jpeg: Uint8Array;
}

export function encodeFrame(header: FrameHeader, jpeg: Uint8Array): ArrayBuffer {
  const head = new TextEncoder().encode(JSON.stringify(header));
  const out = new Uint8Array(6 + head.length + jpeg.length);
  out.set(MAGIC, 0);
  out[4] = (head.length >> 8) & 0xff;
  out[5] = head.length & 0xff;
  out.set(head, 6);
  out.set(jpeg, 6 + head.length);
  return out.buffer;
}

export function parseFrame(buf: ArrayBuffer): Frame | null {
  const bytes = new Uint8Array(buf);
  if (bytes.length < 6 || MAGIC.some((b, i) => bytes[i] !== b)) return null;
  const len = ((bytes[4] ?? 0) << 8) | (bytes[5] ?? 0);
  if (bytes.length < 6 + len) return null;
  let header: FrameHeader;
  try {
    header = JSON.parse(new TextDecoder().decode(bytes.subarray(6, 6 + len))) as FrameHeader;
  } catch {
    return null;
  }
  if (typeof header.cam !== "string") return null;
  return { header, jpeg: bytes.subarray(6 + len) };
}

export type FrameListener = (frame: Frame) => void;
export type CameraErrorListener = (code: string) => void;

export interface VideoOptions {
  width: number;
  fps: number;
}

export class VideoHub {
  private sock: SocketLike | null = null;
  private watchers = new Map<string, Set<FrameListener>>();
  private errorWatchers = new Map<string, Set<CameraErrorListener>>();
  private retry: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private closed = false;

  constructor(
    private readonly url: string,
    private readonly factory: SocketFactory = browserSocket,
    private opts: VideoOptions = { width: 320, fps: 12 },
  ) {}

  setOptions(opts: VideoOptions): void {
    this.opts = opts;
    this.sendSubscription();
  }

  watch(cam: string, onFrame: FrameListener, onError?: CameraErrorListener): () => void {
    const set = this.watchers.get(cam) ?? new Set<FrameListener>();
    const isNew = set.size === 0;
    set.add(onFrame);
    this.watchers.set(cam, set);
    if (onError) {
      const es = this.errorWatchers.get(cam) ?? new Set<CameraErrorListener>();
      es.add(onError);
      this.errorWatchers.set(cam, es);
    }
    this.closed = false;
    if (!this.sock) this.open();
    else if (isNew) this.sendSubscription();
    return () => {
      set.delete(onFrame);
      if (onError) this.errorWatchers.get(cam)?.delete(onError);
      if (set.size === 0) {
        this.watchers.delete(cam);
        this.sendSubscription();
      }
    };
  }

  get cameras(): string[] {
    return [...this.watchers.keys()].sort();
  }

  close(): void {
    this.closed = true;
    if (this.retry) clearTimeout(this.retry);
    this.sock?.close(1000, "bye");
    this.sock = null;
  }

  private sendSubscription(): void {
    if (this.sock?.readyState !== 1) return;
    this.sock.send(
      JSON.stringify({
        type: "subscribe",
        cameras: this.cameras,
        width: this.opts.width,
        fps: this.opts.fps,
      }),
    );
  }

  private dispatch(buf: ArrayBuffer): void {
    const frame = parseFrame(buf);
    if (!frame) return;
    for (const l of this.watchers.get(frame.header.cam) ?? []) l(frame);
  }

  private open(): void {
    let sock: SocketLike;
    try {
      sock = this.factory(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    sock.binaryType = "arraybuffer";
    this.sock = sock;
    sock.onopen = () => {
      this.attempt = 0;
      this.sendSubscription();
    };
    sock.onmessage = (ev: MessageEvent) => {
      const data: unknown = ev.data;
      if (data instanceof ArrayBuffer) this.dispatch(data);
      else if (ArrayBuffer.isView(data)) {
        const bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
        this.dispatch(bytes.slice().buffer);
      } else if (data instanceof Blob) {
        void data.arrayBuffer().then((b) => {
          this.dispatch(b);
        });
      } else if (typeof data === "string") {
        try {
          const msg = JSON.parse(data) as { type?: string; cam?: string; code?: string };
          if (msg.type === "camera_error" && msg.cam) {
            for (const l of this.errorWatchers.get(msg.cam) ?? []) l(msg.code ?? "camera_error");
          }
        } catch {
          /* ignore */
        }
      }
    };
    sock.onclose = () => {
      if (this.sock === sock) this.sock = null;
      if (!this.closed && this.watchers.size > 0) this.scheduleReconnect();
    };
    sock.onerror = () => {
      /* onclose follows */
    };
  }

  private scheduleReconnect(): void {
    const delay = backoffMs(this.attempt);
    this.attempt += 1;
    this.retry = setTimeout(() => {
      this.retry = null;
      if (!this.sock) this.open();
    }, delay);
  }
}
