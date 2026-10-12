// A6 size limit. Real events are about 20 to 40 bytes, so 500 of them cannot
// reach 64 KiB. This test drives the internal transport with a small byte cap
// to prove that an oversized batch is split, in order, with consecutive seq.
import { describe, expect, test } from "vitest";
import { createSigner } from "../src/signing";
import { createTransport } from "../src/transport";
import { Harness, TEST_KEY } from "./harness";

describe("transport byte limit (A6)", () => {
  test("splits a batch whose body would exceed the byte cap", async () => {
    const h = new Harness();
    const transport = createTransport({
      url: "http://collector.test/v1/batches",
      sessionId: "s",
      streamId: "t",
      pointerDevice: "mouse",
      sign: createSigner(TEST_KEY),
      fetchImpl: h.fetchImpl as typeof fetch,
      clock: () => 0,
      flushIntervalMs: 60_000,
      maxBatchEvents: 500,
      maxBatchBytes: 600,
    });
    for (let i = 0; i < 100; i++) transport.push([12, 1000 + i, i]);
    await transport.flush();
    await transport.shutdown();

    expect(h.requests.length).toBeGreaterThan(1);
    for (const r of h.requests) expect(r.bodyBytes.length).toBeLessThanOrEqual(600);
    const batches = h.sentBatches();
    expect(batches.map((b) => b.seq)).toEqual(batches.map((_, i) => i));
    expect(batches.flatMap((b) => b.events.map((e) => e[2]))).toEqual(
      Array.from({ length: 100 }, (_, i) => i),
    );
  });
});
