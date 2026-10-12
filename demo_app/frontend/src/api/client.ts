/**
 * Typed client for the demo backend (docs/interfaces.md section 15).
 * All paths are relative so the Vite proxy keeps the session cookie same-origin.
 */

export type ChannelName = "keystroke" | "pointer" | "interaction";
export type Channels = Record<ChannelName, boolean>;
export type DeclaredDevice = "mouse" | "touchpad";

export interface Consent {
  version: string;
  at: string;
  channels: Channels;
  research_consent: boolean;
  pointer_device: DeclaredDevice;
}

export interface Me {
  username: string;
  consent: Consent | null;
}

export interface LoginResult {
  username: string;
  needs_consent: boolean;
}

export interface ConsentBody {
  version: string;
  channels: Channels;
  research_consent: boolean;
  pointer_device: DeclaredDevice;
}

export interface StreamGrant {
  endpoint: string;
  session_id: string;
  stream_id: string;
  stream_key: string;
  channels: Channels;
  pointer_device: "mouse" | "touchpad" | "unknown";
}

export interface Registry {
  pages: Record<string, number>;
  actions: Record<string, number>;
}

export const CONSENT_VERSION = "1";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }

  /** The `error` code from a JSON error body, for example "no_consent". */
  get code(): string | undefined {
    if (this.body && typeof this.body === "object" && "error" in this.body) {
      const value = (this.body as { error: unknown }).error;
      return typeof value === "string" ? value : undefined;
    }
    return undefined;
  }

  /** Field names from an `invalid_request` body. Empty for other errors. */
  get fields(): string[] {
    if (this.body && typeof this.body === "object" && "fields" in this.body) {
      const value = (this.body as { fields: unknown }).fields;
      if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
    }
    return [];
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin" };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  const text = response.status === 204 ? "" : await response.text();
  const parsed: unknown = text ? safeJson(text) : undefined;
  if (!response.ok) throw new ApiError(response.status, parsed);
  return parsed as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

export const api = {
  register: (username: string, password: string) =>
    request<{ username: string }>("POST", "/api/register", { username, password }),

  login: (username: string, password: string) =>
    request<LoginResult>("POST", "/api/login", { username, password }),

  logout: () => request<void>("POST", "/api/logout"),

  /** Returns null when nobody is signed in. */
  me: async (): Promise<Me | null> => {
    try {
      return await request<Me>("GET", "/api/me");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },

  /** Returns the stored consent object. */
  giveConsent: (body: ConsentBody) => request<Consent>("POST", "/api/consent", body),

  withdrawConsent: () => request<void>("DELETE", "/api/consent"),

  requestStream: () => request<StreamGrant>("POST", "/api/authwho/stream"),

  registry: () => request<Registry>("GET", "/api/registry"),

  sendNote: (text: string) => request<void>("POST", "/api/notes", { text }),

  addPayee: (name: string, account: string) =>
    request<{ ok: boolean }>("POST", "/api/payees", { name, account }),

  exportReports: () => request<{ ok: boolean }>("POST", "/api/reports/export"),
};
