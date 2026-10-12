import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useSession } from "../session/SessionProvider";
import { Button } from "./Button";

const NAV_ITEMS = [
  { to: "/", label: "Home" },
  { to: "/write", label: "Write" },
  { to: "/form", label: "Form" },
  { to: "/payees", label: "Payees" },
  { to: "/reports", label: "Reports" },
  { to: "/settings", label: "Settings" },
];

interface LayoutProps {
  children: ReactNode;
  onSignOut: () => Promise<void>;
}

export function Layout({ children, onSignOut }: LayoutProps) {
  const { session } = useSession();
  const { pathname } = useLocation();
  const previousPath = useRef(pathname);

  // After client-side navigation, move focus to the new page's heading so keyboard and
  // screen reader users start at the top of the new content.
  useEffect(() => {
    if (previousPath.current === pathname) return;
    previousPath.current = pathname;
    document.querySelector<HTMLElement>("[data-page-title]")?.focus();
  }, [pathname]);

  const signedIn = session.status === "signed_in";
  const showAppNav = signedIn && session.consent !== null;

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <a
        href="#main"
        className="sr-only rounded-md bg-paper px-3 py-2 text-sm font-semibold text-accent focus:not-sr-only focus:absolute focus:left-4 focus:top-4"
      >
        Skip to main content
      </a>
      <header className="border-b border-line bg-paper">
        <div className="mx-auto flex max-w-5xl items-center gap-8 px-8 py-4">
          <Link to="/" className="text-base font-semibold text-ink">
            AuthWho demo
          </Link>
          {showAppNav ? (
            <nav aria-label="Main" className="flex-1">
              <ul className="flex gap-1">
                {NAV_ITEMS.map((item) => (
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
          ) : (
            <div className="flex-1" />
          )}
          {signedIn ? (
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted">Signed in as {session.username}</span>
              <Button variant="secondary" onClick={() => void onSignOut()}>
                Sign out
              </Button>
            </div>
          ) : session.status === "signed_out" ? (
            <div className="flex items-center gap-4 text-sm font-medium">
              <Link to="/login" className="text-accent hover:underline">
                Sign in
              </Link>
              <Link to="/register" className="text-accent hover:underline">
                Create account
              </Link>
            </div>
          ) : null}
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-8 py-10">
        {children}
      </main>

      <footer className="border-t border-line bg-paper">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-8 px-8 py-5 text-sm text-muted">
          <p>Typing rhythm and pointer movement are checked only with your consent.</p>
          <Link to="/what-we-collect" className="font-medium text-accent hover:underline">
            What we collect
          </Link>
        </div>
      </footer>
    </div>
  );
}
