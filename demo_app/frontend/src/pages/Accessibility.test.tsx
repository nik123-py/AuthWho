import { screen } from "@testing-library/react";
import { start } from "@authwho/sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createFakeHandle, defaultConsent, type FakeBackendOptions } from "../test/fakeBackend";
import { renderApp } from "../test/renderApp";

vi.mock("@authwho/sdk", () => ({ start: vi.fn() }));

beforeEach(() => {
  vi.mocked(start).mockReset();
  vi.mocked(start).mockReturnValue(createFakeHandle());
});

const loggedOut: FakeBackendOptions = { loggedIn: false };
const noConsent: FakeBackendOptions = { loggedIn: true, consent: null };
const consented: FakeBackendOptions = { loggedIn: true, consent: defaultConsent() };

interface PageCase {
  path: string;
  title: RegExp;
  options: FakeBackendOptions;
  labels: (string | RegExp)[];
}

const PAGES: PageCase[] = [
  { path: "/login", title: /^sign in$/i, options: loggedOut, labels: ["Username", "Password"] },
  {
    path: "/register",
    title: /create an account/i,
    options: loggedOut,
    labels: ["Username", "Password", "Confirm password"],
  },
  { path: "/what-we-collect", title: /what we collect/i, options: loggedOut, labels: [] },
  {
    path: "/consent",
    title: /consent/i,
    options: noConsent,
    labels: [/typing rhythm/i, /pointer movement/i, /page interaction/i, "Mouse", "Touchpad", /research dataset/i, /i agree/i],
  },
  { path: "/", title: /welcome/i, options: consented, labels: [] },
  { path: "/write", title: /^write$/i, options: consented, labels: ["Your note"] },
  {
    path: "/form",
    title: /your details/i,
    options: consented,
    labels: ["Full name", "Email address", "Street address", "City", "Preferred contact method", /monthly summary/i],
  },
  { path: "/payees", title: /payees/i, options: consented, labels: ["Payee name", "Account number"] },
  { path: "/reports", title: /reports/i, options: consented, labels: [] },
  {
    path: "/settings",
    title: /settings/i,
    options: consented,
    labels: [/typing rhythm/i, /pointer movement/i, /page interaction/i, "Mouse", "Touchpad", /research dataset/i],
  },
];

function formControls(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>("input, select, textarea"));
}

function hasAccessibleLabel(control: HTMLElement): boolean {
  const labels = (control as HTMLInputElement).labels;
  const labelText = labels ? Array.from(labels).map((l) => l.textContent?.trim() ?? "").join("") : "";
  return labelText.length > 0 || !!control.getAttribute("aria-label") || !!control.getAttribute("aria-labelledby");
}

describe("B6 every form control has an accessible label", () => {
  for (const page of PAGES) {
    it(`${page.path}`, async () => {
      renderApp(page.path, page.options);
      await screen.findByRole("heading", { level: 1, name: page.title });

      for (const label of page.labels) {
        expect(screen.getByLabelText(label)).toBeInTheDocument();
      }
      const controls = formControls();
      expect(controls.length).toBeGreaterThanOrEqual(page.labels.length);
      const unlabelled = controls.filter((control) => !hasAccessibleLabel(control));
      expect(unlabelled.map((c) => c.outerHTML)).toEqual([]);
    });
  }
});

describe("Keyboard access", () => {
  for (const page of PAGES) {
    it(`${page.path} keeps every control in the natural tab order`, async () => {
      renderApp(page.path, page.options);
      await screen.findByRole("heading", { level: 1, name: page.title });
      const positive = Array.from(document.querySelectorAll("[tabindex]")).filter(
        (el) => Number(el.getAttribute("tabindex")) > 0,
      );
      expect(positive).toEqual([]);
      const removed = Array.from(document.querySelectorAll("input, select, textarea, button, a[href]")).filter(
        (el) => el.getAttribute("tabindex") === "-1",
      );
      expect(removed).toEqual([]);
    });
  }

  it("moves focus to the new page heading after navigation, not on first load", async () => {
    const { user } = renderApp("/", consented);
    const home = await screen.findByRole("heading", { level: 1, name: /welcome/i });
    expect(home).not.toHaveFocus();
    await user.click(screen.getByRole("link", { name: "Write" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Write" })).toHaveFocus();
  });

  it("offers a skip link as the first stop", async () => {
    const { user } = renderApp("/login", loggedOut);
    await screen.findByRole("heading", { level: 1, name: /sign in/i });
    await user.tab();
    const skip = screen.getByRole("link", { name: "Skip to main content" });
    expect(skip).toHaveFocus();
    expect(skip).toHaveAttribute("href", "#main");
    expect(document.getElementById("main")).not.toBeNull();
  });

  it("completes the consent form with the keyboard alone", async () => {
    const { user, backend } = renderApp("/consent", noConsent);
    await screen.findByRole("heading", { level: 1, name: /consent/i });
    screen.getByRole("checkbox", { name: /typing rhythm/i }).focus();
    await user.tab(); // pointer movement
    await user.tab(); // page interaction
    await user.keyboard(" "); // opt out of page interaction
    await user.tab(); // device radio group
    await user.keyboard("{ArrowRight}"); // touchpad
    await user.tab(); // research
    await user.tab(); // I agree
    await user.keyboard(" ");
    await user.tab(); // Give consent
    expect(screen.getByRole("button", { name: /give consent/i })).toHaveFocus();
    await user.keyboard("{Enter}");

    await screen.findByRole("heading", { level: 1, name: /welcome/i });
    expect(backend.callsTo("POST", "/api/consent")[0].body).toEqual({
      version: "1",
      channels: { keystroke: true, pointer: true, interaction: false },
      research_consent: false,
      pointer_device: "touchpad",
    });
  });
});
