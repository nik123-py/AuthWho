import { screen, waitFor, within } from "@testing-library/react";
import { start } from "@authwho/sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createFakeHandle, defaultConsent, type FakeHandle } from "../test/fakeBackend";
import { renderApp } from "../test/renderApp";

vi.mock("@authwho/sdk", () => ({ start: vi.fn() }));

// Copied from README.md "What is and is not collected". If the README changes, this must too.
const README_COLLECTED = [
  "Key-down and key-up times with a coarse key category (letter, digit, space, backspace, modifier, navigation, other).",
  "Pointer coordinates and times, clicks, wheel and scroll movement.",
  "Focus changes between form fields (by position on the page, not by name), page changes, whether copy, cut or paste happened, and whether the tab is visible.",
  "The pointing device the user declared (mouse or touchpad).",
];
const README_NEVER = [
  "Which characters or keys were typed, the contents of any field, or clipboard contents.",
  "Any keystrokes inside password fields.",
  "Names, emails or passwords. AuthWho sees only a pseudonymous user ID.",
];
const README_RETENTION: [string, string][] = [
  ["Raw event batches", "At most 24 hours"],
  ["Window feature vectors", "30 days, rolling"],
  ["Profile templates", "Until re-enrollment or account deletion"],
  ["Decision records", "90 days"],
  ["Volunteer research data (research consent only)", "Until the project ends"],
];

let handle: FakeHandle;
beforeEach(() => {
  handle = createFakeHandle();
  vi.mocked(start).mockReset();
  vi.mocked(start).mockReturnValue(handle);
});

async function openLoggedOut() {
  const view = renderApp("/what-we-collect", { loggedIn: false });
  await screen.findByRole("heading", { level: 1, name: "What we collect" });
  return view;
}

describe("B4 What we collect", () => {
  it("lists every collected signal from the README", async () => {
    await openLoggedOut();
    const list = screen.getByRole("list", { name: /collected only after consent/i });
    for (const item of README_COLLECTED) {
      expect(within(list).getByText(item)).toBeInTheDocument();
    }
    expect(within(list).getAllByRole("listitem")).toHaveLength(README_COLLECTED.length);
  });

  it("lists every never-collected item from the README", async () => {
    await openLoggedOut();
    const list = screen.getByRole("list", { name: /never collected/i });
    for (const item of README_NEVER) {
      expect(within(list).getByText(item)).toBeInTheDocument();
    }
    expect(within(list).getAllByRole("listitem")).toHaveLength(README_NEVER.length);
  });

  it("shows the retention period for every kind of stored data", async () => {
    await openLoggedOut();
    const table = screen.getByRole("table", { name: /how long data is kept/i });
    for (const [data, howLong] of README_RETENTION) {
      const row = within(table).getByRole("row", { name: new RegExp(`^${escape(data)}`) });
      expect(within(row).getByText(howLong)).toBeInTheDocument();
    }
  });

  it("states that AuthWho never disables an account", async () => {
    await openLoggedOut();
    expect(screen.getByText(/it never disables an account/i)).toBeInTheDocument();
  });

  it("is reachable from the footer of the sign-in page while logged out", async () => {
    const { user } = renderApp("/login", { loggedIn: false });
    await screen.findByRole("heading", { level: 1, name: /sign in/i });
    const footer = screen.getByRole("contentinfo");
    await user.click(within(footer).getByRole("link", { name: "What we collect" }));
    expect(await screen.findByRole("heading", { level: 1, name: "What we collect" })).toBeInTheDocument();
  });

  it("is in the footer of every app page for a signed-in user", async () => {
    const { user } = renderApp("/", { loggedIn: true, consent: defaultConsent() });
    await screen.findByRole("link", { name: "Home" });
    for (const page of ["Home", "Write", "Form", "Payees", "Reports", "Settings"]) {
      await user.click(screen.getByRole("link", { name: page }));
      const footer = screen.getByRole("contentinfo");
      expect(within(footer).getByRole("link", { name: "What we collect" })).toHaveAttribute(
        "href",
        "/what-we-collect",
      );
    }
  });

  it("reports the collect page code for a consented user", async () => {
    renderApp("/what-we-collect", { loggedIn: true, consent: defaultConsent() });
    await waitFor(() => expect(handle.setPage).toHaveBeenLastCalledWith(6));
  });
});

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
