// Batching, signing and delivery (docs/interfaces.md section 6).
//
// Events are buffered and moved into an ordered outbox on flush. Batches are
// delivered strictly one at a time, so they are never reordered. A batch is
// serialised and signed once, when it first reaches the head of the outbox,
// and every retry resends those exact bytes with the same seq and nonce.
// `seq` advances only when the collector accepts a batch, so a batch that is
// rejected as invalid leaves its seq for the next one.
import { randomNonce, type Signer } from "./signing";
import type { PointerDevice } from "./types";

export const MAX_EVENTS_PER_BATCH = 500;
export const MAX_BATCH_BYTES = 64 * 1024;

const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 30_000;
const DEFAULT_RETRY_AFTER_S = 1;
/** Attempts per batch once shutdown has begun, so stop() always finishes. */
const ATTEMPTS_WHILE_STOPPING = 3;

export interface TransportOptions {
  url: string;
  sessionId: string;
  streamId: string;
  pointerDevice: PointerDevice;
  sign: Signer;
  fetchImpl: typeof fetch;
  /** Stream-relative time in ms. */
  clock: () => number;
  flushIntervalMs: number;
  maxBatchEvents: number;
  maxBatchBytes?: number;
}

export interface Transport {
  push(event: number[]): void;
  /** Moves buffered events to the outbox and resolves once all are settled. */
  flush(keepalive?: boolean): Promise<void>;
  /** Final flush with bounded retries; stops the timer and further sends. */
  shutdown(): Promise<void>;
}

interface Pending {
  events: number[][];
  keepalive: boolean;
}

type Outcome = "accepted" | "dropped" | "retry" | "fatal";

export function round1(ms: number): number {
  return Math.round(ms * 10) / 10;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function readJson(res: Response): Promise<Record<string, unknown>> {
  try {
    const body: unknown = await res.json();
    return body !== null && typeof body === "object" ? (body as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

export function createTransport(options: TransportOptions): Transport {
  const cap = Math.max(1, Math.min(MAX_EVENTS_PER_BATCH, Math.floor(options.maxBatchEvents)));
  const maxBytes = options.maxBatchBytes ?? MAX_BATCH_BYTES;
  const encoder = new TextEncoder();

  let buffer: number[][] = [];
  const outbox: Pending[] = [];
  let chain: Promise<void> = Promise.resolve();
  let seq = 0;
  let stopping = false;
  let closed = false;

  const timer = setInterval(() => {
    if (buffer.length > 0) void flush(false);
  }, options.flushIntervalMs);

  function push(event: number[]): void {
    if (closed || stopping) return;
    buffer.push(event);
    if (buffer.length >= cap) void flush(false);
  }

  function flush(keepalive = false): Promise<void> {
    if (!closed && buffer.length > 0) {
      for (let i = 0; i < buffer.length; i += cap) {
        outbox.push({ events: buffer.slice(i, i + cap), keepalive });
      }
      buffer = [];
    }
    chain = chain.then(drain);
    return chain;
  }

  async function drain(): Promise<void> {
    while (outbox.length > 0 && !closed) {
      const item = outbox.shift()!;
      try {
        await deliver(item);
      } catch {
        // A failure to serialise or sign drops only this batch.
      }
    }
    if (closed) outbox.length = 0;
  }

  /** Serialises once, splitting off the tail while the body is over the byte cap. */
  function serialise(item: Pending): Uint8Array<ArrayBuffer> {
    let events = item.events;
    for (;;) {
      const text = JSON.stringify({
        v: 1,
        session_id: options.sessionId,
        stream_id: options.streamId,
        seq,
        nonce: randomNonce(),
        sent_at: round1(options.clock()),
        pointer_device: options.pointerDevice,
        events,
      });
      const bytes = encoder.encode(text);
      if (bytes.length <= maxBytes || events.length <= 1) return bytes;
      const half = Math.ceil(events.length / 2);
      outbox.unshift({ events: events.slice(half), keepalive: item.keepalive });
      events = events.slice(0, half);
    }
  }

  async function deliver(item: Pending): Promise<void> {
    const body = serialise(item);
    const signature = await options.sign(body);
    for (let attempt = 1; ; attempt++) {
      if (closed) return;
      let outcome: Outcome;
      let waitMs = Math.min(BACKOFF_BASE_MS * 2 ** (attempt - 1), BACKOFF_MAX_MS);
      try {
        const res = await options.fetchImpl(options.url, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-AuthWho-Signature": signature },
          body,
          keepalive: item.keepalive,
          credentials: "omit",
        });
        if (res.status >= 200 && res.status < 300) {
          outcome = "accepted";
        } else if (res.status === 409) {
          // A retry whose earlier attempt was stored comes back as a duplicate.
          const reply = await readJson(res);
          outcome = reply.reason === "duplicate" ? "accepted" : "dropped";
        } else if (res.status === 429) {
          const reply = await readJson(res);
          const after = typeof reply.retry_after === "number" && reply.retry_after >= 0
            ? reply.retry_after
            : DEFAULT_RETRY_AFTER_S;
          waitMs = after * 1000;
          outcome = "retry";
        } else if (res.status === 408 || res.status >= 500) {
          outcome = "retry";
        } else if (res.status === 401) {
          outcome = "fatal";
        } else {
          outcome = "dropped";
        }
      } catch {
        outcome = "retry";
      }

      if (outcome === "accepted") {
        seq += 1;
        return;
      }
      if (outcome === "dropped") return;
      if (outcome === "fatal") {
        close();
        return;
      }
      if (stopping && attempt >= ATTEMPTS_WHILE_STOPPING) return;
      await sleep(waitMs);
    }
  }

  function close(): void {
    closed = true;
    clearInterval(timer);
    buffer = [];
    outbox.length = 0;
  }

  async function shutdown(): Promise<void> {
    const done = flush(false);
    stopping = true;
    clearInterval(timer);
    await done;
    closed = true;
  }

  return { push, flush, shutdown };
}
