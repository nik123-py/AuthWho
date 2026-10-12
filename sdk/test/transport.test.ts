// A6 batching, A7 signature and A8 delivery behaviour through the public API.
// Events are generated with setPage so these tests do not depend on DOM capture.
import { createHmac } from "node:crypto";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  BATCH_KEYS,
  ENDPOINT,
  Harness,
  SESSION_ID,
  STREAM_ID,
  TEST_KEY,
  accepted,
  jsonResponse,
  settle,
  until,
} from "./harness";

const LONG = 60_000;

function referenceKey(): Uint8Array {
  const b64 = TEST_KEY.replace(/-/g, "+").replace(/_/g, "/") + "=";
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

let h: Harness;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  h = new Harness();
});

afterEach(async () => {
  vi.useRealTimers();
});

describe("batch format (A6)", () => {
  test("a flushed batch has the documented fields and relative times", async () => {
    h.clock = 5000;
    h.start({ pointerDevice: "touchpad" });
    h.advance(12.34);
    h.handle.setPage(3);
    h.advance(100);
    await h.handle.flush();

    expect(h.requests).toHaveLength(1);
    const req = h.requests[0]!;
    expect(req.url).toBe(`${ENDPOINT}/v1/batches`);
    expect(req.headers["content-type"]).toBe("application/json");
    const batch = JSON.parse(req.bodyText);
    expect(Object.keys(batch).sort()).toEqual(BATCH_KEYS);
    expect(batch.v).toBe(1);
    expect(batch.session_id).toBe(SESSION_ID);
    expect(batch.stream_id).toBe(STREAM_ID);
    expect(batch.seq).toBe(0);
    expect(batch.pointer_device).toBe("touchpad");
    expect(batch.sent_at).toBe(112.3);
    expect(batch.events).toEqual([[12, 12.3, 3]]);
  });

  test("an empty buffer sends nothing", async () => {
    h.start();
    await h.handle.flush();
    expect(h.requests).toHaveLength(0);
  });

  test("a trailing slash on the endpoint is not doubled", async () => {
    h.start({ endpoint: `${ENDPOINT}/` });
    h.handle.setPage(1);
    await h.handle.flush();
    expect(h.requests[0]!.url).toBe(`${ENDPOINT}/v1/batches`);
  });
});

describe("batching (A6)", () => {
  test("flushes when the interval elapses and not before", async () => {
    h.start({ flushIntervalMs: 2000 });
    h.handle.setPage(1);
    await vi.advanceTimersByTimeAsync(1999);
    await settle();
    expect(h.requests).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    await until(() => h.requests.length === 1);
    expect(h.sentBatches()[0]!.events).toEqual([[12, 0, 1]]);
  });

  test("the default interval is 2000 ms", async () => {
    h.start();
    h.handle.setPage(1);
    await vi.advanceTimersByTimeAsync(1999);
    await settle();
    expect(h.requests).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    await until(() => h.requests.length === 1);
  });

  test("flushes as soon as the event cap is reached", async () => {
    h.start({ flushIntervalMs: LONG, maxBatchEvents: 5 });
    for (let i = 0; i < 4; i++) h.handle.setPage(i);
    await settle();
    expect(h.requests).toHaveLength(0);
    h.handle.setPage(4);
    await until(() => h.requests.length === 1);
    expect(h.sentBatches()[0]!.events.map((e) => e[2])).toEqual([0, 1, 2, 3, 4]);
  });

  test("the default event cap is 200", async () => {
    h.start({ flushIntervalMs: LONG });
    for (let i = 0; i < 199; i++) h.handle.setPage(i);
    await settle();
    expect(h.requests).toHaveLength(0);
    h.handle.setPage(199);
    await until(() => h.requests.length === 1);
    expect(h.sentBatches()[0]!.events).toHaveLength(200);
  });

  test("seq starts at 0 and increases by one; nonces are unique", async () => {
    h.start({ flushIntervalMs: LONG });
    for (let i = 0; i < 4; i++) {
      h.handle.setPage(i);
      await h.handle.flush();
    }
    const batches = h.sentBatches();
    expect(batches.map((b) => b.seq)).toEqual([0, 1, 2, 3]);
    const nonces = batches.map((b) => b.nonce);
    expect(new Set(nonces).size).toBe(4);
    for (const n of nonces) expect(n).toMatch(/^[A-Za-z0-9_-]{22}$/);
  });

  test("no batch exceeds 500 events even when a larger cap is configured", async () => {
    h.start({ flushIntervalMs: LONG, maxBatchEvents: 1000 });
    for (let i = 0; i < 1200; i++) h.handle.setPage(i);
    await h.handle.flush();
    const batches = h.sentBatches();
    for (const b of batches) expect(b.events.length).toBeLessThanOrEqual(500);
    expect(batches.map((b) => b.seq)).toEqual(batches.map((_, i) => i));
    expect(batches.flatMap((b) => b.events.map((e) => e[2]))).toEqual(
      Array.from({ length: 1200 }, (_, i) => i),
    );
  });

  test("every body stays within 64 KiB", async () => {
    h.start({ flushIntervalMs: LONG, maxBatchEvents: 500 });
    for (let i = 0; i < 2000; i++) h.handle.setPage(2_000_000_000 + i);
    await h.handle.flush();
    for (const r of h.requests) expect(r.bodyBytes.length).toBeLessThanOrEqual(65536);
  });
});

describe("signature (A7)", () => {
  test("X-AuthWho-Signature is the HMAC-SHA256 of the exact body bytes", async () => {
    h.start();
    h.handle.setPage(7);
    h.handle.markAction(2);
    await h.handle.flush();
    h.handle.setPage(8);
    await h.handle.flush();

    expect(h.requests).toHaveLength(2);
    for (const req of h.requests) {
      const expected = createHmac("sha256", referenceKey()).update(req.bodyBytes).digest("base64url");
      expect(req.headers["x-authwho-signature"]).toBe(expected);
    }
  });

  test("a body altered after signing no longer verifies", async () => {
    h.start();
    h.handle.setPage(7);
    await h.handle.flush();
    const req = h.requests[0]!;
    const tampered = new TextEncoder().encode(req.bodyText.replace('"seq":0', '"seq":1'));
    const mac = createHmac("sha256", referenceKey()).update(tampered).digest("base64url");
    expect(req.headers["x-authwho-signature"]).not.toBe(mac);
  });
});

describe("delivery (A8)", () => {
  test("a network failure is retried with the identical body and signature", async () => {
    h.responder = (_req, i) => {
      if (i === 0) throw new TypeError("network down");
      return accepted();
    };
    h.start({ flushIntervalMs: LONG });
    h.handle.setPage(1);
    const done = h.handle.flush();
    await until(() => h.requests.length === 2, 100);
    await done;
    const [first, second] = h.requests;
    expect(second!.bodyText).toBe(first!.bodyText);
    expect(second!.headers["x-authwho-signature"]).toBe(first!.headers["x-authwho-signature"]);

    h.handle.setPage(2);
    await h.handle.flush();
    expect(h.sentBatches()[2]!.seq).toBe(1);
  });

  test("a 5xx response is retried with the identical body", async () => {
    h.responder = (_req, i) => (i === 0 ? jsonResponse(503, {}) : accepted());
    h.start({ flushIntervalMs: LONG });
    h.handle.setPage(1);
    const done = h.handle.flush();
    await until(() => h.requests.length === 2, 100);
    await done;
    expect(h.requests[1]!.bodyText).toBe(h.requests[0]!.bodyText);
  });

  test("409 duplicate for its own retried batch counts as success", async () => {
    h.responder = (_req, i) => {
      if (i === 0) throw new TypeError("response lost");
      if (i === 1) return jsonResponse(409, { error: "replay", reason: "duplicate" });
      return accepted();
    };
    h.start({ flushIntervalMs: LONG });
    h.handle.setPage(1);
    const done = h.handle.flush();
    await until(() => h.requests.length === 2, 100);
    await done;
    await settle();
    expect(h.requests).toHaveLength(2);

    h.handle.setPage(2);
    await h.handle.flush();
    expect(h.sentBatches().map((b) => b.seq)).toEqual([0, 0, 1]);
  });

  test("429 waits for retry_after seconds, then resends the identical body", async () => {
    h.responder = (_req, i) =>
      i === 0 ? jsonResponse(429, { error: "rate_limited", retry_after: 3 }) : accepted();
    h.start({ flushIntervalMs: LONG });
    h.handle.setPage(1);
    const done = h.handle.flush();
    await until(() => h.requests.length === 1);
    await settle();
    await vi.advanceTimersByTimeAsync(2900);
    await settle();
    expect(h.requests).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(100);
    await until(() => h.requests.length === 2);
    await done;
    expect(h.requests[1]!.bodyText).toBe(h.requests[0]!.bodyText);
  });

  test("batches are never reordered while an earlier one is being retried", async () => {
    let failures = 2;
    h.responder = () => {
      if (failures > 0) {
        failures--;
        return jsonResponse(503, {});
      }
      return accepted();
    };
    h.start({ flushIntervalMs: LONG });
    h.handle.setPage(1);
    const first = h.handle.flush();
    await until(() => h.requests.length === 1);
    h.handle.setPage(2);
    const second = h.handle.flush();
    await until(() => h.requests.length === 4, 100);
    await Promise.all([first, second]);
    const batches = h.sentBatches();
    expect(batches.map((b) => b.seq)).toEqual([0, 0, 0, 1]);
    expect(batches.map((b) => b.events[0]![2])).toEqual([1, 1, 1, 2]);
  });

  test("a batch rejected as invalid is dropped and its seq is reused", async () => {
    h.responder = (_req, i) => (i === 0 ? jsonResponse(400, { error: "schema", detail: "x" }) : accepted());
    h.start({ flushIntervalMs: LONG });
    h.handle.setPage(1);
    await h.handle.flush();
    h.handle.setPage(2);
    await h.handle.flush();
    const batches = h.sentBatches();
    expect(batches).toHaveLength(2);
    expect(batches.map((b) => b.seq)).toEqual([0, 0]);
    expect(batches[1]!.events).toEqual([[12, 0, 2]]);
  });

  test("401 ends delivery for the stream", async () => {
    h.responder = () => jsonResponse(401, { error: "unknown_stream" });
    h.start({ flushIntervalMs: LONG });
    h.handle.setPage(1);
    await h.handle.flush();
    h.handle.setPage(2);
    await h.handle.flush();
    expect(h.requests).toHaveLength(1);
  });

  test("visibilitychange to hidden flushes with keepalive", async () => {
    const visibility = vi.spyOn(document, "visibilityState", "get");
    try {
      h.start({ flushIntervalMs: LONG });
      h.handle.setPage(1);
      await h.handle.flush();
      expect(h.requests[0]!.keepalive).toBe(false);

      h.handle.setPage(2);
      visibility.mockReturnValue("hidden");
      document.dispatchEvent(new Event("visibilitychange"));
      await until(() => h.requests.length === 2);
      expect(h.requests[1]!.keepalive).toBe(true);
      expect(h.sentBatches()[1]!.events.some((e) => e[0] === 12 && e[2] === 2)).toBe(true);
    } finally {
      visibility.mockRestore();
      await h.handle.stop();
    }
  });

  test("stop() gives up on an unreachable collector instead of retrying forever", async () => {
    h.responder = () => jsonResponse(503, {});
    h.start({ flushIntervalMs: LONG });
    h.handle.setPage(1);
    let stopped = false;
    void h.handle.stop().then(() => {
      stopped = true;
    });
    await until(() => stopped, 500);
    expect(h.requests.length).toBeLessThanOrEqual(3);
  });
});
