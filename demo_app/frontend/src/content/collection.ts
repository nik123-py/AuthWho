/**
 * The plain-language collection notice. Mirrors README.md "What is and is not collected"
 * and the retention table in proposal Section 9. Keep the three in step.
 */

export const COLLECTED: readonly string[] = [
  "Key-down and key-up times with a coarse key category (letter, digit, space, backspace, modifier, navigation, other).",
  "Pointer coordinates and times, clicks, wheel and scroll movement.",
  "Focus changes between form fields (by position on the page, not by name), page changes, whether copy, cut or paste happened, and whether the tab is visible.",
  "The pointing device the user declared (mouse or touchpad).",
];

export const NEVER_COLLECTED: readonly string[] = [
  "Which characters or keys were typed, the contents of any field, or clipboard contents.",
  "Any keystrokes inside password fields.",
  "Names, emails or passwords. AuthWho sees only a pseudonymous user ID.",
];

export interface RetentionRow {
  data: string;
  where: string;
  howLong: string;
}

export const RETENTION: readonly RetentionRow[] = [
  { data: "Raw event batches", where: "Redis Streams, in memory only", howLong: "At most 24 hours" },
  { data: "Window feature vectors", where: "PostgreSQL, encrypted", howLong: "30 days, rolling" },
  {
    data: "Profile templates",
    where: "PostgreSQL, encrypted",
    howLong: "Until re-enrollment or account deletion",
  },
  { data: "Decision records", where: "PostgreSQL", howLong: "90 days" },
  {
    data: "Volunteer research data (research consent only)",
    where: "Encrypted local files, pseudonymous IDs",
    howLong: "Until the project ends",
  },
];

export const STRONGEST_ACTION =
  "The strongest action AuthWho can take is to ask for a one-time code again or end the session. It never disables an account.";
