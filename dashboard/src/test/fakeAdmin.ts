import { vi } from "vitest";

/** A stand-in for the admin API (docs/interfaces.md section 13) and its live WebSocket. */

export const TOKEN = "admin-token";
export const SID = "11111111-1111-4111-8111-111111111111";
export const SID2 = "22222222-2222-4222-8222-222222222222";

export const sessions = () => [
  { session_id: SID, user_id: "aaaaaaaa-0000-4000-8000-000000000001", app_id: "demo", role: "analyst",
    status: "step_up_required", created_at: "2026-10-14T10:00:00+00:00", ended_at: null, trust: 42.5,
    state: "scored", level: "strong_deviation" },
  { session_id: SID2, user_id: "aaaaaaaa-0000-4000-8000-000000000002", app_id: "demo", role: "analyst",
    status: "active", created_at: "2026-10-14T09:00:00+00:00", ended_at: null, trust: null,
    state: "insufficient_signal", level: "insufficient_signal" },
];

export const timeline = () => [
  { seq: 1, at: "2026-10-14T10:00:05+00:00", state: "scored", trust: 95, confidence: 0.8, bot_flags: [],
    channels: { keystroke: { status: "scored", score: 0.8, fresh: true, top_features: [] },
                pointer: { status: "no_profile", score: null, fresh: false, top_features: [] },
                interaction: { status: "opted_out", score: null, fresh: false, top_features: [] } } },
  { seq: 2, at: "2026-10-14T10:00:20+00:00", state: "scored", trust: 42.5, confidence: 0.9, bot_flags: [],
    channels: { keystroke: { status: "scored", score: 0.05, fresh: true,
                             top_features: [{ name: "flight_median", z: 6.1 }] },
                pointer: { status: "scored", score: 0.1, fresh: true,
                           top_features: [{ name: "velocity_mean", z: -3.2 }] },
                interaction: { status: "opted_out", score: null, fresh: false, top_features: [] } } },
];

export const decisions = () => [
  { decision_id: "d1", created_at: "2026-10-14T10:00:20+00:00", trigger: "trust_update", level: "strong_deviation",
    outcome: "step_up", trust: 42.5, action_code: null, step_up_result: null,
    explanation: "Typing rhythm and mouse movement both diverged from this user's profile, mainly the gap between keys and pointer speed." },
];

export const policies = () => [
  { policy_id: "demo-analyst", app_id: "demo", role: "analyst", high: 75, strong: 50, channel_low: 0.5,
    action_sensitivity: { add_payee: "high", export_report: "high" }, exempt: false, version: 1 },
];

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export function createFakeAdmin(options: { failAuth?: boolean } = {}) {
  const calls: { method: string; path: string; auth: string | null; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = (init.method ?? "GET").toUpperCase();
    const headers = new Headers(init.headers);
    const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ method, path, auth: headers.get("Authorization"), body });
    if (options.failAuth || headers.get("Authorization") !== `Bearer ${TOKEN}`) {
      return json(401, { error: "unauthorized" });
    }
    if (path.startsWith("/v1/admin/sessions?")) return json(200, sessions());
    if (path === `/v1/admin/sessions/${SID}/timeline`) return json(200, timeline());
    if (path === `/v1/admin/sessions/${SID}/decisions`) return json(200, decisions());
    if (path === `/v1/admin/sessions/${SID}/incident-report`) return json(200, { report: "AuthWho incident report" });
    if (path === "/v1/admin/policies" && method === "GET") return json(200, policies());
    if (path === "/v1/admin/policies/demo-analyst" && method === "PUT") {
      return json(200, { ...policies()[0], ...(body as object), version: 2 });
    }
    return json(404, { error: "not_found" });
  });
  return { fetch: fetchMock, calls };
}

/** A WebSocket stand-in the tests can push messages through. */
export class FakeSocket {
  static instances: FakeSocket[] = [];
  url: string;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onopen: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  push(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  close() {
    this.closed = true;
  }
}
