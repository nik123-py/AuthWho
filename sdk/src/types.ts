// Public types of @authwho/sdk (docs/interfaces.md section 14).

export type Channel = "keystroke" | "pointer" | "interaction";
export type PointerDevice = "mouse" | "touchpad" | "unknown";

export interface AuthWhoConfig {
  /** Collector base URL, for example "http://localhost:8000". */
  endpoint: string;
  sessionId: string;
  streamId: string;
  /** Per-stream HMAC key from the stream handshake, base64url, 32 bytes. */
  streamKey: string;
  channels: Record<Channel, boolean>;
  pointerDevice: PointerDevice;
  /** Default 2000. */
  flushIntervalMs?: number;
  /** Default 200. */
  maxBatchEvents?: number;
  /** Default window.document; injectable for tests. */
  root?: Document;
  /** Injectable for tests. */
  fetchImpl?: typeof fetch;
  /** Injectable clock, default performance.now. */
  now?: () => number;
}

export interface AuthWhoHandle {
  setPage(pageCode: number): void;
  markAction(actionCode: number): void;
  flush(): Promise<void>;
  /** Flushes, then removes every listener. */
  stop(): Promise<void>;
}
