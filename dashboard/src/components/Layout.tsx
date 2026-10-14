import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../auth";
import { Button } from "./Button";

const NAV = [
  { to: "/", label: "Sessions" },
  { to: "/live", label: "Live demo" },
  { to: "/policies", label: "Policies" },
];

export function Layout({ children }: { children: ReactNode }) {
  const { token, signOut } = useAuth();
  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <a
        href="#main"
        className="sr-only rounded-md bg-paper px-3 py-2 text-sm font-semibold text-accent focus:not-sr-only focus:absolute focus:left-4 focus:top-4"
      >
        Skip to main content
      </a>
      <header className="border-b border-line bg-paper">
        <div className="mx-auto flex max-w-6xl items-center gap-8 px-8 py-4">
          <span className="text-base font-semibold">AuthWho dashboard</span>
          {token ? (
            <>
              <nav aria-label="Main" className="flex-1">
                <ul className="flex gap-1">
                  {NAV.map((item) => (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.to === "/"}
                        className={({ isActive }) =>
                          `rounded-md px-3 py-2 text-sm font-medium ${
                            isActive ? "bg-accent-soft text-accent-strong" : "text-muted hover:text-ink"
                          }`
                        }
                      >
                        {item.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </nav>
              <Button variant="secondary" onClick={() => signOut()}>
                Sign out
              </Button>
            </>
          ) : null}
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-8 py-10">
        {children}
      </main>
    </div>
  );
}
