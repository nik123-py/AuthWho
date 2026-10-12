import { ApiError } from "./client";

/** Plain-language messages for the demo backend error codes (docs/interfaces.md section 15). */
const MESSAGES: Record<string, string> = {
  username_taken: "That username is taken. Choose another.",
  invalid_credentials: "The username or password is incorrect.",
  not_logged_in: "You are signed out, so this was not saved. Sign in again to continue.",
  authwho_unavailable:
    "The identity check service is not responding, so this was not completed. Try again in a moment.",
  step_up_required: "Confirm it is you, then try again.",
  session_ended: "For your security this session has ended. Sign in again.",
  invalid_code: "That code is not right. Check your authenticator app and try again.",
  totp_already_enabled: "An authenticator app is already set up.",
  totp_unavailable: "Authenticator apps are not available on this server.",
};

/** Labels for the consent body fields, shared by the consent and settings forms. */
export const CONSENT_FIELDS: Record<string, string> = {
  channels: "Signals AuthWho may use",
  pointer_device: "Pointing device",
  research_consent: "Research use",
  version: "Consent version",
};

interface DescribeOptions {
  /** Shown for network failures and codes without a specific message. */
  fallback: string;
  /** API field name to the visible label of the matching form control. */
  fields?: Record<string, string>;
}

export function describeError(error: unknown, { fallback, fields = {} }: DescribeOptions): string {
  if (!(error instanceof ApiError)) return fallback;
  const code = error.code;
  if (code === "invalid_request") {
    const labels = error.fields.map((name) => fields[name] ?? readable(name));
    if (labels.length === 0) return "Some details were not accepted. Check the form and try again.";
    const noun = labels.length === 1 ? "this field" : "these fields";
    return `Check ${noun} and try again: ${labels.join(", ")}.`;
  }
  return (code && MESSAGES[code]) || fallback;
}

function readable(name: string): string {
  const words = name.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
