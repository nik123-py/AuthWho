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

async function openSettings(options = {}) {
  const view = renderApp("/settings", { loggedIn: true, consent: defaultConsent(), ...options });
  await screen.findByRole("heading", { level: 1, name: "Settings" });
  await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
  return view;
}

describe("B5 consent withdrawal", () => {
  it("calls DELETE /api/consent and stops the SDK", async () => {
    const { user, backend } = await openSettings();
    await user.click(screen.getByRole("button", { name: "Withdraw consent" }));
    await user.click(screen.getByRole("button", { name: "Yes, withdraw consent" }));

    await screen.findByText(/consent withdrawn/i);
    expect(backend.callsTo("DELETE", "/api/consent")).toHaveLength(1);
    expect(handle.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("heading", { level: 1, name: /consent/i })).toBeInTheDocument();
    expect(start).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the confirmation is cancelled", async () => {
    const { user, backend } = await openSettings();
    await user.click(screen.getByRole("button", { name: "Withdraw consent" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(backend.callsTo("DELETE", "/api/consent")).toHaveLength(0);
    expect(handle.stop).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Withdraw consent" })).toBeInTheDocument();
  });

  it("stops capture and shows an error when the withdrawal request fails", async () => {
    const { user } = await openSettings({ failures: { "DELETE /api/consent": { status: 502 } } });
    await user.click(screen.getByRole("button", { name: "Withdraw consent" }));
    await user.click(screen.getByRole("button", { name: "Yes, withdraw consent" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/not withdrawn/i);
    expect(handle.stop).toHaveBeenCalledTimes(1);
  });
});

describe("Changing channel choices or device", () => {
  it("shows the current choices", async () => {
    await openSettings({
      consent: defaultConsent({
        channels: { keystroke: true, pointer: false, interaction: true },
        pointer_device: "touchpad",
        research_consent: true,
      }),
    });
    expect(screen.getByRole("checkbox", { name: /typing rhythm/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /pointer movement/i })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /page interaction/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Touchpad" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /research dataset/i })).toBeChecked();
  });

  it("saves new choices and restarts capture with a fresh stream", async () => {
    const { user, backend } = await openSettings();
    await user.click(screen.getByRole("checkbox", { name: /typing rhythm/i }));
    await user.click(screen.getByRole("radio", { name: "Touchpad" }));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await screen.findByText(/changes saved/i);
    expect(backend.callsTo("POST", "/api/consent")).toEqual([
      {
        method: "POST",
        path: "/api/consent",
        body: {
          version: "1",
          channels: { keystroke: false, pointer: true, interaction: true },
          research_consent: false,
          pointer_device: "touchpad",
        },
      },
    ]);
    await waitFor(() => expect(start).toHaveBeenCalledTimes(2));
    expect(handle.stop).toHaveBeenCalledTimes(1);
    expect(vi.mocked(start).mock.calls[1][0]).toMatchObject({
      channels: { keystroke: false, pointer: true, interaction: true },
      pointerDevice: "touchpad",
    });
  });
});
