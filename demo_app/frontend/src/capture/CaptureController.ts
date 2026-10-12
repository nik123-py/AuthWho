import { start, type AuthWhoHandle } from "@authwho/sdk";
import { api, ApiError, type Registry } from "../api/client";

export type StartResult = "started" | "no_consent" | "cancelled";

/**
 * Owns the AuthWho SDK lifecycle for one page load (docs/interfaces.md sections 4 and 14).
 *
 * The frontend never reads or sends input values itself: it only asks the demo backend for a
 * stream, hands the result to the SDK, and tells the SDK which page or action is current using
 * integer codes from the registry. The stream key is passed straight to the SDK and is kept
 * nowhere else.
 */
export class CaptureController {
  private handle: AuthWhoHandle | null = null;
  private registry: Registry | null = null;
  private starting: Promise<StartResult> | null = null;
  private generation = 0;
  private currentPage: string | null = null;

  /** Starts capture once. Concurrent callers share the same attempt. */
  ensureStarted(): Promise<StartResult> {
    if (this.handle) return Promise.resolve("started");
    if (!this.starting) {
      const generation = this.generation;
      this.starting = this.startOnce(generation).finally(() => {
        if (generation === this.generation) this.starting = null;
      });
    }
    return this.starting;
  }

  private async startOnce(generation: number): Promise<StartResult> {
    let grant;
    try {
      [grant, this.registry] = await Promise.all([api.requestStream(), this.registry ?? api.registry()]);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && error.code === "no_consent") return "no_consent";
      throw error;
    }
    // A stop() that arrived while the stream was being requested wins: do not start.
    if (generation !== this.generation) return "cancelled";

    this.handle = start({
      endpoint: grant.endpoint,
      sessionId: grant.session_id,
      streamId: grant.stream_id,
      streamKey: grant.stream_key,
      channels: grant.channels,
      pointerDevice: grant.pointer_device,
    });
    if (this.currentPage) this.sendPage(this.currentPage);
    return "started";
  }

  /** Records the current page by registry key, for example "payees". */
  setPage(pageKey: string | null): void {
    this.currentPage = pageKey;
    if (pageKey) this.sendPage(pageKey);
  }

  private sendPage(pageKey: string): void {
    const code = this.registry?.pages[pageKey];
    if (this.handle && code !== undefined) this.handle.setPage(code);
  }

  /** Marks the start of a sensitive action by registry key, for example "add_payee". */
  markAction(actionKey: string): void {
    const code = this.registry?.actions[actionKey];
    if (this.handle && code !== undefined) this.handle.markAction(code);
  }

  /** Flushes and stops capture. Safe to call when nothing is running. */
  async stop(): Promise<void> {
    this.generation += 1;
    this.starting = null;
    const handle = this.handle;
    this.handle = null;
    if (!handle) return;
    try {
      await handle.stop();
    } catch {
      // The SDK removes its listeners even if the final flush fails; nothing else to undo.
    }
  }

  get running(): boolean {
    return this.handle !== null;
  }
}
