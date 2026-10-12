// @authwho/sdk public API (docs/interfaces.md section 14).
import { attachCapture } from "./capture";
import { createSigner } from "./signing";
import { createTransport, round1 } from "./transport";
import type { AuthWhoConfig, AuthWhoHandle } from "./types";

export type { AuthWhoConfig, AuthWhoHandle, Channel, PointerDevice } from "./types";
export { categoryOf } from "./category";

const DEFAULT_FLUSH_INTERVAL_MS = 2000;
const DEFAULT_MAX_BATCH_EVENTS = 200;
const PAGE = 12;
const ACTION_MARK = 13;

/**
 * Starts capture for one stream. The stream key from the handshake is held
 * only in memory for signing; it is never stored, logged or sent.
 */
export function start(config: AuthWhoConfig): AuthWhoHandle {
  const root = config.root ?? window.document;
  const view = root.defaultView;
  const now = config.now ?? (() => performance.now());
  const fetchImpl = config.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const t0 = now();
  const clock = (): number => round1(now() - t0);
  // Event times come from event.timeStamp, which current browsers report on
  // the same clock as performance.now(), so handler delay does not distort
  // dwell and flight times. A timeStamp that is 0, not finite, or later than
  // now() (so not on that clock) falls back to the handler time.
  const timeOf = (e: Event): number => {
    const handled = now();
    const stamp = e.timeStamp;
    const at = Number.isFinite(stamp) && stamp > 0 && stamp <= handled ? stamp : handled;
    return round1(at - t0);
  };

  const transport = createTransport({
    url: `${config.endpoint.replace(/\/+$/, "")}/v1/batches`,
    sessionId: config.sessionId,
    streamId: config.streamId,
    pointerDevice: config.pointerDevice,
    sign: createSigner(config.streamKey),
    fetchImpl,
    clock,
    flushIntervalMs: config.flushIntervalMs ?? DEFAULT_FLUSH_INTERVAL_MS,
    maxBatchEvents: config.maxBatchEvents ?? DEFAULT_MAX_BATCH_EVENTS,
  });

  // Capture listeners are added first so that a VISIBILITY event recorded on
  // the same visibilitychange is included in the keepalive flush below.
  const capture = attachCapture({
    root,
    channels: config.channels,
    clock,
    timeOf,
    emit: (event) => transport.push(event),
  });

  const onVisibility = (): void => {
    if (root.visibilityState === "hidden") void transport.flush(true);
  };
  const onPageHide = (): void => {
    void transport.flush(true);
  };
  root.addEventListener("visibilitychange", onVisibility);
  view?.addEventListener("pagehide", onPageHide);

  const mark = (code: number, value: number): void => {
    if (!config.channels.interaction || !Number.isInteger(value)) return;
    transport.push([code, clock(), value]);
  };

  return {
    setPage: (pageCode) => mark(PAGE, pageCode),
    markAction: (actionCode) => mark(ACTION_MARK, actionCode),
    flush: () => transport.flush(false),
    stop: async () => {
      // detach() first hands any pending trailing event to the transport;
      // shutdown() then moves the whole buffer to the outbox. Both run
      // synchronously, so no event can arrive between them.
      capture.detach();
      root.removeEventListener("visibilitychange", onVisibility);
      view?.removeEventListener("pagehide", onPageHide);
      await transport.shutdown();
    },
  };
}
