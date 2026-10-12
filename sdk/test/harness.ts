// Test utilities: start the SDK against a recording fetch and a manual clock,
// and dispatch realistic DOM events. Test-only code; never imported by src/.
import { vi } from "vitest";
import { start, type AuthWhoConfig, type AuthWhoHandle } from "../src/index";

// Captured before any test installs fake timers.
const realSetTimeout = globalThis.setTimeout;

// Browsers stamp events on the performance.now() clock; jsdom stamps them with
// Date.now(). So that events and the injected clock agree, every event in
// these tests reports the active harness clock as its timeStamp at the moment
// it is read. A test can still give one event its own timeStamp with
// withTimeStamp(), which shadows this getter on that instance.
let activeHarness: Harness | null = null;
const nativeTimeStamp = Object.getOwnPropertyDescriptor(Event.prototype, "timeStamp")!;
Object.defineProperty(Event.prototype, "timeStamp", {
  configurable: true,
  enumerable: nativeTimeStamp.enumerable,
  get(this: Event): number {
    return activeHarness ? activeHarness.clock : (nativeTimeStamp.get!.call(this) as number);
  },
});

/** Gives one event a fixed timeStamp, as a browser does at creation time. */
export function withTimeStamp<E extends Event>(event: E, timeStamp: number): E {
  Object.defineProperty(event, "timeStamp", { configurable: true, value: timeStamp });
  return event;
}

/** Lets real asynchronous work (WebCrypto, promise chains) progress. */
export function realTick(): Promise<void> {
  return new Promise((resolve) => realSetTimeout(resolve, 0));
}

/**
 * Waits until `cond` holds. Each step yields to the real event loop and, when
 * fake timers are installed, advances fake time by `stepMs`. Returns the fake
 * time advanced.
 */
export async function until(cond: () => boolean, stepMs = 0, maxSteps = 500): Promise<number> {
  let advanced = 0;
  for (let i = 0; i < maxSteps; i++) {
    if (cond()) return advanced;
    await realTick();
    if (cond()) return advanced;
    if (stepMs > 0 && vi.isFakeTimers()) {
      await vi.advanceTimersByTimeAsync(stepMs);
      advanced += stepMs;
    }
  }
  throw new Error("until: condition not met");
}

/** Yields to the real event loop several times without advancing fake time. */
export async function settle(times = 20): Promise<void> {
  for (let i = 0; i < times; i++) await realTick();
}

// 32 bytes 0x00..0x1f in base64url without padding.
export const TEST_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8";
export const SESSION_ID = "11111111-1111-4111-8111-111111111111";
export const STREAM_ID = "22222222-2222-4222-8222-222222222222";
export const ENDPOINT = "http://collector.test";

export const BATCH_KEYS = [
  "events",
  "nonce",
  "pointer_device",
  "sent_at",
  "seq",
  "session_id",
  "stream_id",
  "v",
];

export interface SentRequest {
  url: string;
  headers: Record<string, string>;
  bodyText: string;
  bodyBytes: Uint8Array;
  keepalive: boolean;
}

export type Responder = (req: SentRequest, index: number) => Response | Promise<Response>;

export interface Batch {
  v: number;
  session_id: string;
  stream_id: string;
  seq: number;
  nonce: string;
  sent_at: number;
  pointer_device: string;
  events: number[][];
}

export function accepted(seq = 0): Response {
  return new Response(JSON.stringify({ accepted: true, seq }), { status: 202 });
}

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

// jsdom and Node have separate realms, so instanceof checks on typed arrays
// are unreliable here; ArrayBuffer.isView works across realms.
function toBytes(body: unknown): Uint8Array {
  if (typeof body === "string") return new TextEncoder().encode(body);
  if (ArrayBuffer.isView(body)) {
    return new Uint8Array(body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength));
  }
  throw new Error("unexpected body type in test fetch");
}

function headerRecord(h: HeadersInit | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  new Headers(h).forEach((value, name) => {
    out[name] = value;
  });
  return out;
}

export class Harness {
  readonly requests: SentRequest[] = [];
  /** Requests that received a 2xx response, in order. */
  readonly acceptedRequests: SentRequest[] = [];
  clock = 0;
  responder: Responder = () => accepted();
  handle!: AuthWhoHandle;

  readonly fetchImpl = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const bodyBytes = toBytes(init?.body);
    const req: SentRequest = {
      url: String(input),
      headers: headerRecord(init?.headers),
      bodyText: new TextDecoder().decode(bodyBytes),
      bodyBytes,
      keepalive: init?.keepalive === true,
    };
    this.requests.push(req);
    const res = await this.responder(req, this.requests.length - 1);
    if (res.status >= 200 && res.status < 300) this.acceptedRequests.push(req);
    return res;
  };

  start(overrides: Partial<AuthWhoConfig> = {}): AuthWhoHandle {
    activeHarness = this;
    this.handle = start({
      endpoint: ENDPOINT,
      sessionId: SESSION_ID,
      streamId: STREAM_ID,
      streamKey: TEST_KEY,
      channels: { keystroke: true, pointer: true, interaction: true },
      pointerDevice: "mouse",
      root: document,
      fetchImpl: this.fetchImpl as typeof fetch,
      now: () => this.clock,
      ...overrides,
    });
    return this.handle;
  }

  advance(ms: number): void {
    this.clock += ms;
  }

  /** Every batch that was sent, parsed, including retries. */
  sentBatches(): Batch[] {
    return this.requests.map((r) => JSON.parse(r.bodyText) as Batch);
  }

  /** Events from accepted batches, in order. */
  events(): number[][] {
    return this.acceptedRequests.flatMap((r) => (JSON.parse(r.bodyText) as Batch).events);
  }

  eventsOfCode(code: number): number[][] {
    return this.events().filter((e) => e[0] === code);
  }
}

// DOM helpers --------------------------------------------------------------

export interface KeyInit {
  key: string;
  code?: string;
  repeat?: boolean;
}

export function keyDown(target: EventTarget, init: KeyInit): void {
  target.dispatchEvent(
    new KeyboardEvent("keydown", { bubbles: true, cancelable: true, composed: true, ...init }),
  );
}

export function keyUp(target: EventTarget, init: KeyInit): void {
  target.dispatchEvent(
    new KeyboardEvent("keyup", { bubbles: true, cancelable: true, composed: true, ...init }),
  );
}

function codeFor(ch: string): string {
  if (/^[a-z]$/i.test(ch)) return `Key${ch.toUpperCase()}`;
  if (/^[0-9]$/.test(ch)) return `Digit${ch}`;
  if (ch === " ") return "Space";
  if (ch === "!") return "Digit1";
  if (ch === "?") return "Slash";
  return "Unidentified";
}

function needsShift(ch: string): boolean {
  return /^[A-Z!?@#$%^&*()]$/.test(ch);
}

/**
 * Types text the way a browser reports it: optional Shift press around the
 * character, keydown, value change, input event, keyup. The value is written
 * so that a capture bug that read it would leak it into the batch.
 */
export function typeText(
  el: HTMLInputElement | HTMLTextAreaElement,
  text: string,
  advance: (ms: number) => void,
): void {
  el.focus();
  // Track the value locally so the harness itself never reads el.value; the
  // no-characters test traps every read of the value getter.
  let current = "";
  for (const ch of text) {
    const shift = needsShift(ch);
    if (shift) {
      keyDown(el, { key: "Shift", code: "ShiftLeft" });
      advance(40);
    }
    keyDown(el, { key: ch, code: codeFor(ch) });
    current += ch;
    el.value = current;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: ch, inputType: "insertText" }));
    advance(80);
    keyUp(el, { key: ch, code: codeFor(ch) });
    advance(30);
    if (shift) {
      keyUp(el, { key: "Shift", code: "ShiftLeft" });
      advance(50);
    }
    advance(60);
  }
}

/** Dispatches a clipboard event whose payload getter records any access. */
export function clipboard(
  target: EventTarget,
  type: "copy" | "cut" | "paste",
  text: string,
  onRead: () => void,
): void {
  const ev = new Event(type, { bubbles: true, cancelable: true, composed: true });
  Object.defineProperty(ev, "clipboardData", {
    get() {
      onRead();
      return {
        getData: () => text,
        types: ["text/plain"],
      };
    },
  });
  target.dispatchEvent(ev);
}

export function pointer(
  target: EventTarget,
  type: "pointermove" | "pointerdown" | "pointerup",
  x: number,
  y: number,
  extra: PointerEventInit = {},
): void {
  target.dispatchEvent(
    new PointerEvent(type, {
      bubbles: true,
      cancelable: true,
      composed: true,
      clientX: x,
      clientY: y,
      pointerType: "mouse",
      button: type === "pointermove" ? -1 : 0,
      ...extra,
    }),
  );
}
