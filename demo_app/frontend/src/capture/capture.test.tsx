import { screen, waitFor } from "@testing-library/react";
import { start } from "@authwho/sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createFakeHandle, defaultConsent, STREAM_KEY, type FakeHandle } from "../test/fakeBackend";
import { renderApp } from "../test/renderApp";

vi.mock("@authwho/sdk", () => ({ start: vi.fn() }));

let handle: FakeHandle;

beforeEach(() => {
  handle = createFakeHandle();
  vi.mocked(start).mockReset();
  vi.mocked(start).mockReturnValue(handle);
});

const nav = (name: string) => screen.getByRole("link", { name });

describe("B2 SDK start", () => {
  it("does not request a stream or start the SDK before consent", async () => {
    const { backend } = renderApp("/consent", { loggedIn: true, consent: null });
    await screen.findByRole("heading", { level: 1, name: /consent/i });
    expect(start).not.toHaveBeenCalled();
    expect(backend.callsTo("POST", "/api/authwho/stream")).toHaveLength(0);
  });

  it("does not start the SDK for a logged-out visitor", async () => {
    const { backend } = renderApp("/what-we-collect", { loggedIn: false });
    await screen.findByRole("heading", { level: 1, name: /what we collect/i });
    expect(start).not.toHaveBeenCalled();
    expect(backend.callsTo("POST", "/api/authwho/stream")).toHaveLength(0);
  });

  it("starts the SDK after consent with the channels returned by the stream endpoint", async () => {
    const { user } = renderApp("/consent", {
      loggedIn: true,
      consent: null,
      stream: { channels: { keystroke: true, pointer: false, interaction: true } },
    });
    await screen.findByRole("heading", { level: 1, name: /consent/i });
    await user.click(screen.getByRole("radio", { name: "Touchpad" }));
    await user.click(screen.getByRole("checkbox", { name: /i agree/i }));
    expect(start).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /give consent/i }));

    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(start).toHaveBeenCalledWith(
      expect.objectContaining({
        endpoint: "http://localhost:8000",
        sessionId: "11111111-1111-4111-8111-111111111111",
        streamId: "22222222-2222-4222-8222-222222222222",
        streamKey: STREAM_KEY,
        channels: { keystroke: true, pointer: false, interaction: true },
        pointerDevice: "touchpad",
      }),
    );
  });

  it("requests a stream and starts the SDK on page load for a consented user", async () => {
    const { backend } = renderApp("/", {
      loggedIn: true,
      consent: defaultConsent(),
      stream: { channels: { keystroke: false, pointer: true, interaction: false } },
    });
    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(backend.callsTo("POST", "/api/authwho/stream")).toHaveLength(1);
    expect(vi.mocked(start).mock.calls[0][0].channels).toEqual({
      keystroke: false,
      pointer: true,
      interaction: false,
    });
  });

  it("sends the user to the consent page without starting the SDK on 409 no_consent", async () => {
    renderApp("/", { loggedIn: true, consent: defaultConsent(), streamNoConsent: true });
    expect(await screen.findByRole("heading", { level: 1, name: /consent/i })).toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
  });

  it("keeps the stream key out of browser storage", async () => {
    renderApp("/", { loggedIn: true, consent: defaultConsent() });
    await waitFor(() => expect(start).toHaveBeenCalled());
    const stored = JSON.stringify({ ...window.localStorage }) + JSON.stringify({ ...window.sessionStorage });
    expect(stored).not.toContain(STREAM_KEY);
    expect(document.cookie).not.toContain(STREAM_KEY);
  });
});

describe("B3 page codes and action marks", () => {
  it("calls setPage with the registry code on every route change", async () => {
    const { user } = renderApp("/", { loggedIn: true, consent: defaultConsent() });
    await waitFor(() => expect(handle.setPage).toHaveBeenLastCalledWith(1));

    const expected: [string, number][] = [
      ["Write", 2],
      ["Form", 3],
      ["Payees", 4],
      ["Reports", 5],
      ["Settings", 7],
      ["What we collect", 6],
      ["Home", 1],
    ];
    for (const [link, code] of expected) {
      await user.click(nav(link));
      await waitFor(() => expect(handle.setPage).toHaveBeenLastCalledWith(code));
    }
  });

  it("calls markAction before the add-payee request", async () => {
    const { user, backend } = renderApp("/payees", { loggedIn: true, consent: defaultConsent() });
    await waitFor(() => expect(start).toHaveBeenCalled());
    await user.type(await screen.findByLabelText("Payee name"), "Ravi Kumar");
    await user.type(screen.getByLabelText("Account number"), "12345678");
    await user.click(screen.getByRole("button", { name: "Add payee" }));

    await screen.findByText(/payee added/i);
    expect(handle.markAction).toHaveBeenCalledWith(1);
    expect(backend.callsTo("POST", "/api/payees")).toEqual([
      { method: "POST", path: "/api/payees", body: { name: "Ravi Kumar", account: "12345678" } },
    ]);
    const markOrder = handle.markAction.mock.invocationCallOrder[0];
    expect(markOrder).toBeLessThan(backend.callOrderOf("POST", "/api/payees")!);
  });

  it("calls markAction before the export request", async () => {
    const { user, backend } = renderApp("/reports", { loggedIn: true, consent: defaultConsent() });
    await waitFor(() => expect(start).toHaveBeenCalled());
    await user.click(await screen.findByRole("button", { name: /export/i }));

    await screen.findByText(/export started/i);
    expect(handle.markAction).toHaveBeenCalledWith(2);
    const markOrder = handle.markAction.mock.invocationCallOrder[0];
    expect(markOrder).toBeLessThan(backend.callOrderOf("POST", "/api/reports/export")!);
  });
});

describe("SDK stop on sign-out", () => {
  it("stops the SDK and then signs out", async () => {
    const { user, backend } = renderApp("/", { loggedIn: true, consent: defaultConsent() });
    await waitFor(() => expect(start).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Sign out" }));

    await screen.findByRole("heading", { level: 1, name: /sign in/i });
    expect(handle.stop).toHaveBeenCalledTimes(1);
    expect(handle.stop.mock.invocationCallOrder[0]).toBeLessThan(backend.callOrderOf("POST", "/api/logout")!);
  });
});
