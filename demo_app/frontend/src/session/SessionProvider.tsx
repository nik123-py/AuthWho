import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api, type Consent, type LoginResult } from "../api/client";

export type Session =
  | { status: "loading" }
  | { status: "signed_out" }
  | {
      status: "signed_in";
      username: string;
      consent: Consent | null;
      /** True after the user withdrew consent in this page load, so the consent page can confirm it. */
      consentWithdrawn?: boolean;
    };

interface SessionContextValue {
  session: Session;
  /** Reloads the signed-in user and consent from GET /api/me. */
  refresh: () => Promise<void>;
  signIn: (username: string, password: string) => Promise<LoginResult>;
  signOut: () => Promise<void>;
  /** Records the consent object the backend stored. */
  setConsent: (consent: Consent) => void;
  /** Marks consent as absent after a withdrawal or a 409 no_consent answer. */
  clearConsent: (reason: "withdrawn" | "missing") => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>({ status: "loading" });

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setSession(
        me ? { status: "signed_in", username: me.username, consent: me.consent } : { status: "signed_out" },
      );
    } catch {
      setSession({ status: "signed_out" });
    }
  }, []);

  // Load once per page load, even when StrictMode runs effects twice in development.
  const loaded = useRef(false);
  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    void refresh();
  }, [refresh]);

  const signIn = useCallback(
    async (username: string, password: string) => {
      const result = await api.login(username, password);
      await refresh();
      return result;
    },
    [refresh],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setSession({ status: "signed_out" });
    }
  }, []);

  const clearConsent = useCallback((reason: "withdrawn" | "missing") => {
    setSession((current) =>
      current.status === "signed_in"
        ? { ...current, consent: null, consentWithdrawn: reason === "withdrawn" }
        : current,
    );
  }, []);

  const setConsent = useCallback((consent: Consent) => {
    setSession((current) =>
      current.status === "signed_in" ? { ...current, consent, consentWithdrawn: false } : current,
    );
  }, []);

  const value = useMemo(
    () => ({ session, refresh, signIn, signOut, setConsent, clearConsent }),
    [session, refresh, signIn, signOut, setConsent, clearConsent],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
