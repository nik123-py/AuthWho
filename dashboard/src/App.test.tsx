import { StrictMode } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { FakeSocket, SID, TOKEN, createFakeAdmin } from "./test/fakeAdmin";

vi.mock("chart.js/auto", () => ({ default: class { destroy() {} update() {} data = { datasets: [] }; } }));

function renderAt(path: string, options: { signedIn?: boolean; failAuth?: boolean } = {}) {
  const admin = createFakeAdmin({ failAuth: options.failAuth });
  vi.stubGlobal("fetch", admin.fetch);
  vi.stubGlobal("WebSocket", FakeSocket);
  if (options.signedIn !== false) window.sessionStorage.setItem("authwho_admin_token", TOKEN);
  const user = userEvent.setup();
  render(
    <StrictMode>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </StrictMode>,
  );
  return { admin, user };
}

beforeEach(() => {
  FakeSocket.instances = [];
});

describe("Sign in", () => {
  it("asks for the admin token and then shows the sessions", async () => {
    const { user, admin } = renderAt("/", { signedIn: false });
    await user.type(await screen.findByLabelText("Admin token"), TOKEN);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sessions" })).toBeInTheDocument();
    expect(admin.calls.every((c) => c.auth === `Bearer ${TOKEN}`)).toBe(true);
  });

  it("returns to sign in with a message when the token is rejected", async () => {
    renderAt("/", { failAuth: true });
    expect(await screen.findByRole("alert")).toHaveTextContent(/token was not accepted/i);
    expect(screen.getByLabelText("Admin token")).toBeInTheDocument();
  });
});

describe("Sessions", () => {
  it("lists sessions with trust, level and Cannot determine for insufficient signal", async () => {
    renderAt("/");
    const table = await screen.findByRole("table", { name: "Sessions" });
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("42.5");
    expect(rows[1]).toHaveTextContent("Strong deviation");
    expect(rows[1]).toHaveTextContent("Step-up required");
    expect(rows[2]).toHaveTextContent("Cannot determine");
  });

  it("updates a session's trust live from the WebSocket", async () => {
    renderAt("/");
    await screen.findByRole("table", { name: "Sessions" });
    await waitFor(() => expect(FakeSocket.instances.length).toBeGreaterThan(0));
    const socket = FakeSocket.instances.at(-1)!;
    expect(socket.url).toContain(`/v1/admin/ws?token=${TOKEN}`);
    act(() => socket.push({ type: "trust", data: { session_id: SID, state: "scored", trust: 12.25 } }));
    expect(await screen.findByText("12.3")).toBeInTheDocument();
  });
});

describe("Session detail", () => {
  it("shows every decision with its explanation, the channel breakdown and the trust table", async () => {
    renderAt(`/sessions/${SID}`);
    expect(await screen.findByText(/both diverged from this user's profile/)).toBeInTheDocument();
    const breakdown = screen.getByRole("region", { name: "Channel breakdown" });
    expect(within(breakdown).getByText("Typing rhythm")).toBeInTheDocument();
    expect(within(breakdown).getByText(/the gap between keys/)).toBeInTheDocument();
    expect(within(breakdown).getByText("Opted out")).toBeInTheDocument();
    const data = screen.getByRole("table", { name: "Trust over time" });
    expect(within(data).getAllByRole("row")).toHaveLength(3);
  });

  it("downloads the incident report", async () => {
    const { user, admin } = renderAt(`/sessions/${SID}`);
    const createUrl = vi.fn(() => "blob:report");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: vi.fn() }));
    await user.click(await screen.findByRole("button", { name: "Export incident report" }));
    await waitFor(() => expect(createUrl).toHaveBeenCalled());
    expect(admin.calls.some((c) => c.path === `/v1/admin/sessions/${SID}/incident-report`)).toBe(true);
  });
});

describe("Live demo", () => {
  it("follows the session that most recently changed and shows its latest explanation", async () => {
    renderAt("/live");
    await screen.findByRole("heading", { level: 1, name: "Live demo" });
    await waitFor(() => expect(FakeSocket.instances.length).toBeGreaterThan(0));
    const socket = FakeSocket.instances.at(-1)!;
    act(() => socket.push({ type: "trust", data: { session_id: SID, state: "scored", trust: 33.0, seq: 5,
      at: "2026-10-14T10:01:00Z", channels: {} } }));
    act(() => socket.push({ type: "decision", data: { session_id: SID, outcome: "step_up", level: "strong_deviation",
      explanation: "Typing rhythm and mouse movement both diverged from this user's profile." } }));
    expect(await screen.findByText("33.0")).toBeInTheDocument();
    expect(screen.getByText("Typing rhythm and mouse movement both diverged from this user's profile.")).toBeInTheDocument();
  });
});

describe("Policies", () => {
  it("saves thresholds and refuses a strong threshold above the high one", async () => {
    const { user, admin } = renderAt("/policies");
    const high = await screen.findByLabelText("Moderate below (trust)");
    const strong = screen.getByLabelText("Strong below (trust)");
    await user.clear(strong);
    await user.type(strong, "80");
    await user.click(screen.getByRole("button", { name: "Save policy" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/must be lower/i);
    await user.clear(strong);
    await user.type(strong, "45");
    await user.clear(high);
    await user.type(high, "80");
    await user.click(screen.getByRole("button", { name: "Save policy" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/saved, version 2/i);
    const put = admin.calls.find((c) => c.method === "PUT")!;
    expect(put.body).toMatchObject({ high: 80, strong: 45, channel_low: 0.5, exempt: false });
  });
});
