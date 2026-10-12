import { screen, waitFor } from "@testing-library/react";
import { start } from "@authwho/sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createFakeHandle, defaultConsent, type FakeHandle } from "../test/fakeBackend";
import { renderApp } from "../test/renderApp";

vi.mock("@authwho/sdk", () => ({ start: vi.fn() }));

let handle: FakeHandle;
beforeEach(() => {
  handle = createFakeHandle();
  vi.mocked(start).mockReset();
  vi.mocked(start).mockReturnValue(handle);
});

const consented = { loggedIn: true, consent: defaultConsent() };
const UNAVAILABLE = { status: 502, body: { error: "authwho_unavailable" } };
const SIGNED_OUT = { status: 401, body: { error: "not_logged_in" } };
const UNAVAILABLE_TEXT = "The identity check service is not responding, so this was not completed. Try again in a moment.";
const SIGNED_OUT_TEXT = "You are signed out, so this was not saved. Sign in again to continue.";

type User = ReturnType<typeof renderApp>["user"];

async function fillRegister(user: User, password: string) {
  await user.type(await screen.findByLabelText("Username"), "ravi");
  await user.type(screen.getByLabelText("Password"), password);
  await user.type(screen.getByLabelText("Confirm password"), password);
  await user.click(screen.getByRole("button", { name: "Create account" }));
}

describe("Register form password rule", () => {
  it("tells the user the minimum length next to the password field", async () => {
    renderApp("/register");
    expect(await screen.findByLabelText("Password")).toHaveAccessibleDescription(
      "At least 8 characters.",
    );
  });

  it("does not send a password shorter than 8 characters", async () => {
    const { user, backend } = renderApp("/register");
    await fillRegister(user, "short12");
    expect(screen.getByRole("alert")).toHaveTextContent("Use a password of at least 8 characters.");
    expect(backend.callsTo("POST", "/api/register")).toHaveLength(0);
  });

  it("does not send a password longer than 1024 characters", async () => {
    const { user, backend } = renderApp("/register");
    await user.type(await screen.findByLabelText("Username"), "ravi");
    const long = "a".repeat(1025);
    await user.click(screen.getByLabelText("Password"));
    await user.paste(long);
    await user.click(screen.getByLabelText("Confirm password"));
    await user.paste(long);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Use a password of at most 1024 characters.");
    expect(backend.callsTo("POST", "/api/register")).toHaveLength(0);
  });

  it("names the field the server rejected", async () => {
    const { user } = renderApp("/register", {
      failures: { "POST /api/register": { status: 422, body: { error: "invalid_request", fields: ["username"] } } },
    });
    await fillRegister(user, "correct horse");
    expect(await screen.findByRole("alert")).toHaveTextContent("Check this field and try again: Username.");
  });

  it("explains that usernames are not case-sensitive", async () => {
    renderApp("/register");
    expect(await screen.findByLabelText("Username")).toHaveAccessibleDescription(
      "Capital letters do not matter: Asha and asha are the same username.",
    );
  });
});

describe("Error codes on each page", () => {
  it("sign in: authwho_unavailable", async () => {
    const { user } = renderApp("/login", { failures: { "POST /api/login": UNAVAILABLE } });
    await user.type(await screen.findByLabelText("Username"), "asha");
    await user.type(screen.getByLabelText("Password"), "correct horse");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(UNAVAILABLE_TEXT);
  });

  it("consent: authwho_unavailable keeps the user on the consent page", async () => {
    const { user } = renderApp("/consent", {
      loggedIn: true,
      consent: null,
      failures: { "POST /api/consent": UNAVAILABLE },
    });
    await user.click(await screen.findByRole("radio", { name: "Mouse" }));
    await user.click(screen.getByRole("checkbox", { name: /i agree/i }));
    await user.click(screen.getByRole("button", { name: /give consent/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(UNAVAILABLE_TEXT);
    expect(screen.getByRole("heading", { level: 1, name: /consent/i })).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
  });

  it("settings: authwho_unavailable when saving", async () => {
    const { user } = renderApp("/settings", { ...consented, failures: { "POST /api/consent": UNAVAILABLE } });
    await user.click(await screen.findByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(UNAVAILABLE_TEXT);
  });

  it("settings: authwho_unavailable when withdrawing still stops capture", async () => {
    const { user } = renderApp("/settings", { ...consented, failures: { "DELETE /api/consent": UNAVAILABLE } });
    await waitFor(() => expect(start).toHaveBeenCalled());
    await user.click(await screen.findByRole("button", { name: "Withdraw consent" }));
    await user.click(screen.getByRole("button", { name: "Yes, withdraw consent" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(UNAVAILABLE_TEXT);
    expect(alert).toHaveTextContent("Capture has stopped on this page.");
    expect(handle.stop).toHaveBeenCalled();
  });

  it("write: not_logged_in", async () => {
    const { user } = renderApp("/write", { ...consented, failures: { "POST /api/notes": SIGNED_OUT } });
    await user.type(await screen.findByLabelText("Your note"), "Some words.");
    await user.click(screen.getByRole("button", { name: "Send note" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(SIGNED_OUT_TEXT);
  });

  it("payees: invalid_request names the account number field", async () => {
    const { user } = renderApp("/payees", {
      ...consented,
      failures: { "POST /api/payees": { status: 422, body: { error: "invalid_request", fields: ["account"] } } },
    });
    await user.type(await screen.findByLabelText("Payee name"), "Ravi Kumar");
    await user.type(screen.getByLabelText("Account number"), "12");
    await user.click(screen.getByRole("button", { name: "Add payee" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Check this field and try again: Account number.");
  });

  it("payees: not_logged_in", async () => {
    const { user } = renderApp("/payees", { ...consented, failures: { "POST /api/payees": SIGNED_OUT } });
    await user.type(await screen.findByLabelText("Payee name"), "Ravi Kumar");
    await user.type(screen.getByLabelText("Account number"), "12345678");
    await user.click(screen.getByRole("button", { name: "Add payee" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(SIGNED_OUT_TEXT);
  });

  it("reports: authwho_unavailable", async () => {
    const { user } = renderApp("/reports", { ...consented, failures: { "POST /api/reports/export": UNAVAILABLE } });
    await user.click(await screen.findByRole("button", { name: "Export reports" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(UNAVAILABLE_TEXT);
  });
});

describe("Stored consent and consenting again", () => {
  it("uses the consent object returned by POST /api/consent", async () => {
    const { user, backend } = renderApp("/consent", { loggedIn: true, consent: null });
    await user.click(await screen.findByRole("radio", { name: "Touchpad" }));
    await user.click(screen.getByRole("checkbox", { name: /i agree/i }));
    await user.click(screen.getByRole("button", { name: /give consent/i }));
    await screen.findByRole("heading", { level: 1, name: /welcome/i });
    expect(backend.callsTo("GET", "/api/me")).toHaveLength(1);

    await user.click(screen.getByRole("link", { name: "Settings" }));
    expect(await screen.findByRole("radio", { name: "Touchpad" })).toBeChecked();
  });

  it("starts a new stream when the user consents again after withdrawing", async () => {
    const { user, backend } = renderApp("/settings", consented);
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    await user.click(await screen.findByRole("button", { name: "Withdraw consent" }));
    await user.click(screen.getByRole("button", { name: "Yes, withdraw consent" }));
    await screen.findByText(/consent withdrawn/i);

    await user.click(screen.getByRole("radio", { name: "Mouse" }));
    await user.click(screen.getByRole("checkbox", { name: /i agree/i }));
    await user.click(screen.getByRole("button", { name: /give consent/i }));
    await waitFor(() => expect(start).toHaveBeenCalledTimes(2));
    expect(backend.callsTo("POST", "/api/authwho/stream")).toHaveLength(2);
  });
});
