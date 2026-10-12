import { screen, waitFor, within } from "@testing-library/react";
import { start } from "@authwho/sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PASSWORD, TOTP_SECRET, createFakeHandle, defaultConsent } from "../test/fakeBackend";
import type { FakeHandle } from "../test/fakeBackend";
import { renderApp } from "../test/renderApp";

vi.mock("@authwho/sdk", () => ({ start: vi.fn() }));

let handle: FakeHandle;
beforeEach(() => {
  handle = createFakeHandle();
  vi.mocked(start).mockReset();
  vi.mocked(start).mockReturnValue(handle);
});

const consented = { loggedIn: true, consent: defaultConsent() };

async function addPayee(user: ReturnType<typeof renderApp>["user"]) {
  await user.type(await screen.findByLabelText("Payee name"), "Ravi");
  await user.type(screen.getByLabelText("Account number"), "12345");
  await user.click(screen.getByRole("button", { name: "Add payee" }));
}

describe("Step-up", () => {
  it("asks for the password when a high-risk action needs a step-up, then the retry succeeds", async () => {
    const { user, backend } = renderApp("/payees", { ...consented, requireStepUp: true });
    await addPayee(user);
    const dialog = await screen.findByRole("dialog", { name: "Confirm it is you" });
    expect(within(dialog).getByText(/never shows any score/i)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Password"), PASSWORD);
    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(backend.callsTo("POST", "/api/step-up")[0].body).toEqual({ password: PASSWORD });
    expect(await screen.findByRole("status")).toHaveTextContent(/confirmed/i);
    await user.click(screen.getByRole("button", { name: "Add payee" }));
    expect(await screen.findByText(/payee added/i)).toBeInTheDocument();
  });

  it("asks for an authenticator code when TOTP is set up", async () => {
    const { user, backend } = renderApp("/payees", { ...consented, requireStepUp: true, totpEnabled: true });
    await addPayee(user);
    const dialog = await screen.findByRole("dialog", { name: "Confirm it is you" });
    await user.type(within(dialog).getByLabelText("Authenticator code"), "123456");
    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(backend.callsTo("POST", "/api/step-up")[0].body).toEqual({ code: "123456" });
  });

  it("opens when the session status says a step-up is required, without any action", async () => {
    renderApp("/write", { ...consented, sessionStatus: "step_up_required" });
    expect(await screen.findByRole("dialog", { name: "Confirm it is you" })).toBeInTheDocument();
  });

  it("shows the attempts left after a wrong answer", async () => {
    const { user } = renderApp("/payees", { ...consented, requireStepUp: true });
    await addPayee(user);
    const dialog = await screen.findByRole("dialog", { name: "Confirm it is you" });
    await user.type(within(dialog).getByLabelText("Password"), "wrong password");
    await user.click(within(dialog).getByRole("button", { name: "Confirm" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("That was not right. 2 attempts left.");
  });

  it("stops capture and shows the session-ended page after three wrong answers", async () => {
    const { user } = renderApp("/payees", { ...consented, requireStepUp: true });
    await addPayee(user);
    const dialog = await screen.findByRole("dialog", { name: "Confirm it is you" });
    for (let i = 0; i < 3; i++) {
      const field = within(dialog).getByLabelText("Password");
      await user.clear(field);
      await user.type(field, "wrong password");
      await user.click(within(dialog).getByRole("button", { name: "Confirm" }));
      if (i < 2) await within(dialog).findByText(/attempts? left/);
    }
    expect(await screen.findByRole("heading", { level: 1, name: "Your session has ended" })).toBeInTheDocument();
    expect(handle.stop).toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute("href", "/login");
  });

  it("goes to the session-ended page when any request reports the session ended", async () => {
    const { user } = renderApp("/write", {
      ...consented,
      failures: { "POST /api/notes": { status: 401, body: { error: "session_ended" } } },
    });
    await user.type(await screen.findByLabelText("Your note"), "hello");
    await user.click(screen.getByRole("button", { name: "Send note" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Your session has ended" })).toBeInTheDocument();
  });
});

describe("Settings", () => {
  it("sets up an authenticator app with the shown key and a code", async () => {
    const { user } = renderApp("/settings", consented);
    await user.click(await screen.findByRole("button", { name: "Set up an authenticator app" }));
    expect(await screen.findByText(TOTP_SECRET)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Code from your authenticator app"), "000000");
    await user.click(screen.getByRole("button", { name: "Confirm code" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/code is not right/i);
    const field = screen.getByLabelText("Code from your authenticator app");
    await user.clear(field);
    await user.type(field, "123456");
    await user.click(screen.getByRole("button", { name: "Confirm code" }));
    expect(await screen.findByText(/authenticator app is set up/i)).toBeInTheDocument();
  });

  it("shows a notice while a consent withdrawal is still being completed", async () => {
    renderApp("/consent", { loggedIn: true, consent: null, withdrawalPending: true });
    expect(await screen.findByText(/still deleting your behavioural data/i)).toBeInTheDocument();
  });
});
