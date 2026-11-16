/**
 * Control WebSocket client (§5.3): hello handshake, 250 ms dead-man heartbeat, reconnect with
 * capped exponential backoff, and immediate e-stop / control messages.
 */
import type { ClientMessage, ServerMessage } from "../api/types";
import type { StationStore } from "./store";

/** The subset of the browser WebSocket used here (the mock station implements the same). */
export interface SocketLike {
  readonly readyState: number;
  binaryType: BinaryType;
  onopen: ((ev: Event) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export type SocketFactory = (url: string) => SocketLike;

export const browserSocket: SocketFactory = (url) => new WebSocket(url);

export const HEARTBEAT_MS = 250;
const OPEN = 1;

export function backoffMs(attempt: number): number {
  return Math.min(5000, 250 * 2 ** Math.min(attempt, 5));
}

export class ControlSocket {
  private sock: SocketLike | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private stopped = false;

  constructor(
    private readonly url: string,
    private readonly store: StationStore,
    private readonly factory: SocketFactory = browserSocket,
    /** Called after every (re)connect so the UI can refresh REST state (GET /status). */
    private readonly onOpen?: () => void,
  ) {}

  start(): void {
    this.stopped = false;
    this.open();
  }

  stop(): void {
    this.stopped = true;
    if (this.retry) clearTimeout(this.retry);
    this.stopHeartbeat();
    this.sock?.close(1000, "bye");
    this.sock = null;
    this.store.setConn("closed");
  }

  get isOpen(): boolean {
    return this.sock?.readyState === OPEN;
  }

  /** Returns false when the socket is not open (the caller then falls back to REST). */
  send(msg: ClientMessage): boolean {
    if (this.sock?.readyState !== OPEN) return false;
    this.sock.send(JSON.stringify(msg));
    return true;
  }

  estop(): boolean {
    return this.send({ type: "estop" });
  }

  private open(): void {
    let sock: SocketLike;
    try {
      sock = this.factory(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.sock = sock;
    sock.onopen = () => {
      this.attempt = 0;
      this.store.setConn("open");
      this.send({ type: "hello", v: 1, client: "station-ui", heartbeat: true });
      this.startHeartbeat();
      this.onOpen?.();
    };
    sock.onmessage = (ev: MessageEvent) => {
      if (typeof ev.data !== "string") return;
      let msg: ServerMessage;
      try {
        msg = JSON.parse(ev.data) as ServerMessage;
      } catch {
        return;
      }
      this.store.handle(msg);
    };
    sock.onclose = () => {
      this.stopHeartbeat();
      if (this.sock === sock) this.sock = null;
      if (!this.stopped) this.scheduleReconnect();
    };
    sock.onerror = () => {
      /* onclose follows */
    };
  }

  private scheduleReconnect(): void {
    this.store.setConn("reconnecting");
    const delay = backoffMs(this.attempt);
    this.attempt += 1;
    this.retry = setTimeout(() => {
      this.open();
    }, delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeat = setInterval(() => {
      this.send({ type: "heartbeat" });
    }, HEARTBEAT_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.heartbeat = null;
  }
}
