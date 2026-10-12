import { vi } from "vitest";

/** A stateful stand-in for the demo backend API in docs/interfaces.md section 15. */

export interface RecordedCall {
  method: string;
  path: string;
  body: unknown;
}

export interface FakeConsent {
  version: string;
  at: string;
  channels: { keystroke: boolean; pointer: boolean; interaction: boolean };
  research_consent: boolean;
  pointer_device: "mouse" | "touchpad";
}

export interface FakeBackendOptions {
  loggedIn?: boolean;
  username?: string;
  consent?: FakeConsent | null;
  /** Overrides for the stream response. Channels default to the consent channels. */
  stream?: Partial<StreamBody>;
  /** Forces the stream endpoint to answer 409 no_consent even when consent exists. */
  streamNoConsent?: boolean;
  /** Per-route status overrides, keyed "METHOD /api/path". */
  failures?: Record<string, { status: number; body?: unknown }>;
}

export interface StreamBody {
  endpoint: string;
  session_id: string;
  stream_id: string;
  stream_key: string;
  channels: { keystroke: boolean; pointer: boolean; interaction: boolean };
  pointer_device: "mouse" | "touchpad" | "unknown";
}

export const REGISTRY = {
  pages: { home: 1, write: 2, form: 3, payees: 4, reports: 5, collect: 6, settings: 7 },
  actions: { add_payee: 1, export_report: 2 },
};

export const STREAM_KEY = "c3RyZWFtLWtleS1zdHJlYW0ta2V5LXN0cmVhbS1rZXk";

export const defaultConsent = (overrides: Partial<FakeConsent> = {}): FakeConsent => ({
  version: "1",
  at: "2026-10-09T10:00:00Z",
  channels: { keystroke: true, pointer: true, interaction: true },
  research_consent: false,
  pointer_device: "mouse",
  ...overrides,
});

function json(status: number, body?: unknown): Response {
  if (body === undefined) return new Response(null, { status });
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function createFakeBackend(options: FakeBackendOptions = {}) {
  const state = {
    loggedIn: options.loggedIn ?? false,
    username: options.username ?? "asha",
    consent: options.consent === undefined ? null : options.consent,
  };
  const calls: RecordedCall[] = [];

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = (init.method ?? "GET").toUpperCase();
    const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ method, path, body });

    const forced = options.failures?.[`${method} ${path}`];
    if (forced) return json(forced.status, forced.body);

    switch (`${method} ${path}`) {
      case "POST /api/register":
        if (typeof body.password !== "string" || body.password.length < 8 || body.password.length > 1024) {
          return json(422, { error: "invalid_request", fields: ["password"] });
        }
        return json(201, { username: body.username });
      case "POST /api/login":
        state.loggedIn = true;
        state.username = body.username;
        return json(200, { username: body.username, needs_consent: state.consent === null });
      case "POST /api/logout":
        state.loggedIn = false;
        return json(204);
      case "GET /api/registry":
        return json(200, REGISTRY);
    }
    if (!state.loggedIn) return json(401, { error: "not_logged_in" });

    switch (`${method} ${path}`) {
      case "GET /api/me":
        return json(200, { username: state.username, consent: state.consent });
      case "POST /api/consent":
        state.consent = {
          version: body.version,
          at: "2026-10-09T10:05:00Z",
          channels: body.channels,
          research_consent: body.research_consent,
          pointer_device: body.pointer_device,
        };
        return json(200, state.consent);
      case "DELETE /api/consent":
        state.consent = null;
        return json(204);
      case "POST /api/authwho/stream": {
        if (state.consent === null || options.streamNoConsent) {
          return json(409, { error: "no_consent" });
        }
        const stream: StreamBody = {
          endpoint: "http://localhost:8000",
          session_id: "11111111-1111-4111-8111-111111111111",
          stream_id: "22222222-2222-4222-8222-222222222222",
          stream_key: STREAM_KEY,
          channels: state.consent.channels,
          pointer_device: state.consent.pointer_device,
          ...options.stream,
        };
        return json(200, stream);
      }
      case "POST /api/notes":
        return json(204);
      case "POST /api/payees":
        return json(200, { ok: true });
      case "POST /api/reports/export":
        return json(200, { ok: true });
    }
    return json(404, { error: "not_found" });
  });

  const callsTo = (method: string, path: string) =>
    calls.filter((c) => c.method === method && c.path === path);

  /** Index into fetchMock.mock.invocationCallOrder of the first call to a route. */
  const callOrderOf = (method: string, path: string) => {
    const index = calls.findIndex((c) => c.method === method && c.path === path);
    return index === -1 ? undefined : fetchMock.mock.invocationCallOrder[index];
  };

  return { fetch: fetchMock, calls, callsTo, callOrderOf, state };
}

export type FakeBackend = ReturnType<typeof createFakeBackend>;

export function createFakeHandle() {
  return {
    setPage: vi.fn<(pageCode: number) => void>(),
    markAction: vi.fn<(actionCode: number) => void>(),
    flush: vi.fn(async () => {}),
    stop: vi.fn(async () => {}),
  };
}

export type FakeHandle = ReturnType<typeof createFakeHandle>;
