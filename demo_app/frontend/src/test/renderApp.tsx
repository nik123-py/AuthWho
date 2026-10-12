import { StrictMode } from "react";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { App } from "../App";
import { createFakeBackend, type FakeBackendOptions } from "./fakeBackend";

/** Renders the whole app at a route against a fake demo backend, in StrictMode as main.tsx does. */
export function renderApp(path: string, options: FakeBackendOptions = {}) {
  const backend = createFakeBackend(options);
  vi.stubGlobal("fetch", backend.fetch);
  const user = userEvent.setup();
  const view = render(
    <StrictMode>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </StrictMode>,
  );
  return { ...view, backend, user };
}
