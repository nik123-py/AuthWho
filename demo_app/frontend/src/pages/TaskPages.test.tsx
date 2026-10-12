import { screen, within } from "@testing-library/react";
import { start } from "@authwho/sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createFakeHandle, defaultConsent } from "../test/fakeBackend";
import { renderApp } from "../test/renderApp";

vi.mock("@authwho/sdk", () => ({ start: vi.fn() }));

beforeEach(() => {
  vi.mocked(start).mockReset();
  vi.mocked(start).mockReturnValue(createFakeHandle());
});

const consented = { loggedIn: true, consent: defaultConsent() };

describe("Write page", () => {
  it("shows a writing prompt", async () => {
    renderApp("/write", consented);
    await screen.findByRole("heading", { level: 1, name: "Write" });
    expect(screen.getByText(/describe/i)).toBeInTheDocument();
  });

  it("sends the note to /api/notes and clears the box", async () => {
    const { user, backend } = renderApp("/write", consented);
    const box = await screen.findByLabelText("Your note");
    await user.type(box, "A quiet morning by the river.");
    await user.click(screen.getByRole("button", { name: "Send note" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/note sent/i);
    expect(backend.callsTo("POST", "/api/notes")).toEqual([
      { method: "POST", path: "/api/notes", body: { text: "A quiet morning by the river." } },
    ]);
    expect(box).toHaveValue("");
  });

  it("asks for some text before sending", async () => {
    const { user, backend } = renderApp("/write", consented);
    await user.click(await screen.findByRole("button", { name: "Send note" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Write something before sending.");
    expect(backend.callsTo("POST", "/api/notes")).toHaveLength(0);
  });
});

describe("Form page", () => {
  it("has name, email, address, city, a select and a checkbox", async () => {
    renderApp("/form", consented);
    expect(await screen.findByLabelText("Full name")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Email address")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Street address")).toBeInTheDocument();
    expect(screen.getByLabelText("City")).toBeInTheDocument();
    const select = screen.getByLabelText("Preferred contact method");
    expect(select.tagName).toBe("SELECT");
    expect(within(select).getAllByRole("option").length).toBeGreaterThan(1);
    expect(screen.getByRole("checkbox", { name: /monthly summary/i })).not.toBeChecked();
  });

  it("confirms the details without sending them anywhere", async () => {
    const { user, backend } = renderApp("/form", consented);
    await user.type(await screen.findByLabelText("Full name"), "Asha Rao");
    await user.type(screen.getByLabelText("Email address"), "asha@example.com");
    await user.type(screen.getByLabelText("Street address"), "12 Lake Road");
    await user.type(screen.getByLabelText("City"), "Pune");
    await user.selectOptions(screen.getByLabelText("Preferred contact method"), "Phone");
    await user.click(screen.getByRole("checkbox", { name: /monthly summary/i }));
    const before = backend.calls.length;
    await user.click(screen.getByRole("button", { name: "Check details" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/details look complete/i);
    expect(backend.calls.slice(before)).toEqual([]);
  });

  it("lists missing required fields", async () => {
    const { user } = renderApp("/form", consented);
    await user.click(await screen.findByRole("button", { name: "Check details" }));
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Enter your full name.");
    expect(alert).toHaveTextContent("Enter your email address.");
  });
});

describe("Home page", () => {
  it("links to every task", async () => {
    renderApp("/", consented);
    const main = await screen.findByRole("main");
    await screen.findByRole("heading", { level: 1, name: /welcome, asha/i });
    for (const name of [/write a note/i, /fill in a form/i, /add a payee/i, /export reports/i]) {
      expect(within(main).getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("never shows a trust score", async () => {
    renderApp("/", consented);
    await screen.findByRole("heading", { level: 1, name: /welcome/i });
    expect(document.body).not.toHaveTextContent(/trust score|score:/i);
  });
});

describe("Unknown pages", () => {
  it("shows a not found page with a way back", async () => {
    renderApp("/nowhere", consented);
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the home page" })).toHaveAttribute("href", "/");
  });
});
