/** Typed client for the AuthWho admin API (docs/interfaces.md section 13). */

export type Level =
  | "insufficient_signal"
  | "high_confidence"
  | "moderate_deviation"
  | "strong_deviation"
  | "critical";

export interface SessionRow {
  session_id: string;
  user_id: string;
  app_id: string;
  role: string;
  status: string;
  created_at: string;
  ended_at: string | null;
  trust: number | null;
  state: string | null;
  level: Level | null;
}

export interface TopFeature {
  name: string;
  z: number;
}

export interface ChannelState {
  status: string;
  score: number | null;
  fresh?: boolean;
  top_features: TopFeature[];
}

export interface TrustPoint {
  seq: number;
  at: string;
  state: string;
  trust: number | null;
  confidence: number | null;
  channels: Record<string, ChannelState>;
  bot_flags: { kind: string; severity: string; evidence: string }[];
}

export interface Decision {
  decision_id: string;
  created_at: string;
  trigger: string;
  level: Level;
  outcome: string;
  trust: number | null;
  action_code: string | null;
  step_up_result: string | null;
  explanation: string;
}

export interface Policy {
  policy_id: string;
  app_id: string;
  role: string;
  high: number;
  strong: number;
  channel_low: number;
  action_sensitivity: Record<string, string>;
  exempt: boolean;
  version: number;
}

const TOKEN_KEY = "authwho_admin_token";

export function storedToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function storeToken(token: string | null) {
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    else window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Without session storage the token lives only in memory for this page.
  }
}

export class Unauthorized extends Error {}

async function request<T>(token: string, method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  const init: RequestInit = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  if (response.status === 401) throw new Unauthorized();
  const parsed = await response.json().catch(() => undefined);
  if (!response.ok) {
    const detail = (parsed as { detail?: string; error?: string } | undefined) ?? {};
    throw new Error(detail.detail ?? detail.error ?? `Request failed with status ${response.status}`);
  }
  return parsed as T;
}

export function adminApi(token: string) {
  return {
    sessions: () => request<SessionRow[]>(token, "GET", "/v1/admin/sessions?limit=100"),
    timeline: (sid: string) => request<TrustPoint[]>(token, "GET", `/v1/admin/sessions/${sid}/timeline`),
    decisions: (sid: string) => request<Decision[]>(token, "GET", `/v1/admin/sessions/${sid}/decisions`),
    incidentReport: (sid: string) => request<unknown>(token, "GET", `/v1/admin/sessions/${sid}/incident-report`),
    policies: () => request<Policy[]>(token, "GET", "/v1/admin/policies"),
    savePolicy: (policy: Policy) =>
      request<Policy>(token, "PUT", `/v1/admin/policies/${policy.policy_id}`, {
        high: policy.high,
        strong: policy.strong,
        channel_low: policy.channel_low,
        action_sensitivity: policy.action_sensitivity,
        exempt: policy.exempt,
      }),
  };
}

export function liveUrl(token: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/v1/admin/ws?token=${encodeURIComponent(token)}`;
}
