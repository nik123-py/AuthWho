import { screen } from "@testing-library/react";
import { start } from "@authwho/sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createFakeHandle, defaultConsent } from "../test/fakeBackend";
import { renderApp } from "../test/renderApp";

vi.mock("@authwho/sdk", () => ({ start: vi.fn() }));

beforeEach(() => {
  vi.mocked(start).mockReset();
  vi.mocked(start).mockReturnValue(createFakeHandle());
});

async function signIn(user: ReturnType<typeof renderApp>["user"], username = "asha", password = "correct horse") {
  await user.type(await screen.findByLabelText("Username"), username);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("Sign in", () => {
  it("uses a password field for the password", async () => {
    renderApp("/login");
    expect(await screen.findByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("sends a user without consent to the consent page", async () => {
    const { user, backend } = renderApp("/login", { consent: null });
    await signIn(user);
    expect(await screen.findByRole("heading", { level: 1, name: /consent/i })).toBeInTheDocument();
    expect(backend.callsTo("POST", "/api/login")[0].body).toEqual({ username: "asha", password: "correct horse" });
    expect(start).not.toHaveBeenCalled();
  });

  it("sends a consented user to the home page", async () => {
    const { user } = renderApp("/login", { consent: defaultConsent() });
    await signIn(user);
    expect(await screen.findByRole("heading", { level: 1, name: /welcome/i })).toBeInTheDocument();
  });

  it("returns to the page the user asked for", async () => {
    const { user } = renderApp("/payees", { consent: defaultConsent() });
    await screen.findByRole("heading", { level: 1, name: /sign in/i });
    await signIn(user);
    expect(await screen.findByRole("heading", { level: 1, name: "Payees" })).toBeInTheDocument();
  });

  it("explains a failed sign-in without saying which part was wrong", async () => {
    const { user } = renderApp("/login", {
      failures: { "POST /api/login": { status: 401, body: { error: "invalid_credentials" } } },
    });
    await signIn(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("The username or password is incorrect.");
  });

  it("asks for both fields before sending anything", async () => {
    const { user, backend } = renderApp("/login");
    await user.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/enter your username and password/i);
    expect(backend.callsTo("POST", "/api/login")).toHaveLength(0);
  });

  it("links to account creation", async () => {
    const { user } = renderApp("/login");
    await user.click(await screen.findByRole("link", { name: "Create an account" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Create an account" })).toBeInTheDocument();
  });
});

describe("Create an account", () => {
  async function fill(user: ReturnType<typeof renderApp>["user"], confirm = "correct horse") {
    await user.type(await screen.findByLabelText("Username"), "ravi");
    await user.type(screen.getByLabelText("Password"), "correct horse");
    await user.type(screen.getByLabelText("Confirm password"), confirm);
    await user.click(screen.getByRole("button", { name: "Create account" }));
  }

  it("creates the account, signs in and asks for consent", async () => {
    const { user, backend } = renderApp("/register");
    await fill(user);
    expect(await screen.findByRole("heading", { level: 1, name: /consent/i })).toBeInTheDocument();
    expect(backend.callsTo("POST", "/api/register")[0].body).toEqual({ username: "ravi", password: "correct horse" });
    expect(backend.callsTo("POST", "/api/login")).toHaveLength(1);
  });

  it("explains a taken username", async () => {
    const { user } = renderApp("/register", {
      failures: { "POST /api/register": { status: 409, body: { error: "username_taken" } } },
    });
    await fill(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("That username is taken. Choose another.");
  });

  it("stops when the passwords do not match", async () => {
    const { user, backend } = renderApp("/register");
    await fill(user, "something else");
    expect(screen.getByRole("alert")).toHaveTextContent("The passwords do not match.");
    expect(backend.callsTo("POST", "/api/register")).toHaveLength(0);
  });
});
