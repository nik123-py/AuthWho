import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/renderApp";

vi.mock("@authwho/sdk", () => ({ start: vi.fn() }));

async function openConsent() {
  const view = renderApp("/consent", { loggedIn: true, consent: null });
  await screen.findByRole("heading", { level: 1, name: /consent/i });
  return view;
}

const submitButton = () => screen.getByRole("button", { name: /give consent/i });

describe("B1 consent form", () => {
  it("defaults every channel to on, research consent to off and no device", async () => {
    await openConsent();
    expect(screen.getByRole("checkbox", { name: /typing rhythm/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /pointer movement/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /page interaction/i })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /research dataset/i })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Mouse" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Touchpad" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /i agree/i })).not.toBeChecked();
  });

  it("explains that unticking a channel opts out of it", async () => {
    await openConsent();
    expect(screen.getByText(/untick a channel to opt out/i)).toBeInTheDocument();
  });

  it("does not submit without the agreement or a device choice", async () => {
    const { user, backend } = await openConsent();
    await user.click(submitButton());
    expect(backend.callsTo("POST", "/api/consent")).toHaveLength(0);
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText(/choose mouse or touchpad/i)).toBeInTheDocument();
    expect(within(alert).getByText(/tick .*i agree/i)).toBeInTheDocument();
  });

  it("does not submit with a device choice but no agreement", async () => {
    const { user, backend } = await openConsent();
    await user.click(screen.getByRole("radio", { name: "Mouse" }));
    await user.click(submitButton());
    expect(backend.callsTo("POST", "/api/consent")).toHaveLength(0);
    expect(screen.getByRole("alert")).toHaveTextContent(/i agree/i);
  });

  it("does not submit with the agreement but no device choice", async () => {
    const { user, backend } = await openConsent();
    await user.click(screen.getByRole("checkbox", { name: /i agree/i }));
    await user.click(submitButton());
    expect(backend.callsTo("POST", "/api/consent")).toHaveLength(0);
    expect(screen.getByRole("alert")).toHaveTextContent(/choose mouse or touchpad/i);
  });

  it("submits the section 15 body including opt-outs", async () => {
    const { user, backend } = await openConsent();
    await user.click(screen.getByRole("checkbox", { name: /page interaction/i }));
    await user.click(screen.getByRole("radio", { name: "Touchpad" }));
    await user.click(screen.getByRole("checkbox", { name: /research dataset/i }));
    await user.click(screen.getByRole("checkbox", { name: /i agree/i }));
    await user.click(submitButton());

    await screen.findByRole("heading", { level: 1, name: /welcome/i });
    expect(backend.callsTo("POST", "/api/consent")).toEqual([
      {
        method: "POST",
        path: "/api/consent",
        body: {
          version: "1",
          channels: { keystroke: true, pointer: true, interaction: false },
          research_consent: true,
          pointer_device: "touchpad",
        },
      },
    ]);
  });

  it("states what is collected, what is never collected and the retention periods", async () => {
    await openConsent();
    expect(screen.getByRole("heading", { name: /what we collect/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /what we never collect/i })).toBeInTheDocument();
    const retention = screen.getByRole("table", { name: /how long data is kept/i });
    expect(within(retention).getByText("At most 24 hours")).toBeInTheDocument();
    expect(within(retention).getByText("30 days, rolling")).toBeInTheDocument();
    expect(within(retention).getByText("90 days")).toBeInTheDocument();
  });

  it("sends a logged-out visitor to the sign-in page", async () => {
    renderApp("/consent", { loggedIn: false });
    expect(await screen.findByRole("heading", { level: 1, name: /sign in/i })).toBeInTheDocument();
  });
});
