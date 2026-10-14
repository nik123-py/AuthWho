import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Unauthorized, adminApi, storeToken, storedToken } from "./api";

interface AuthValue {
  token: string | null;
  notice: string | null;
  signIn: (token: string) => void;
  signOut: (notice?: string) => void;
  api: ReturnType<typeof adminApi> | null;
  /** Runs an API call; a 401 signs out with a message instead of throwing. */
  guard: <T>(call: () => Promise<T>) => Promise<T | undefined>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => storedToken());
  const [notice, setNotice] = useState<string | null>(null);

  const signIn = useCallback((t: string) => {
    storeToken(t);
    setNotice(null);
    setToken(t);
  }, []);

  const signOut = useCallback((message?: string) => {
    storeToken(null);
    setNotice(message ?? null);
    setToken(null);
  }, []);

  const api = useMemo(() => (token ? adminApi(token) : null), [token]);

  const guard = useCallback(
    async <T,>(call: () => Promise<T>) => {
      try {
        return await call();
      } catch (error) {
        if (error instanceof Unauthorized) {
          signOut("The admin token was not accepted. Sign in again.");
          return undefined;
        }
        throw error;
      }
    },
    [signOut],
  );

  const value = useMemo(() => ({ token, notice, signIn, signOut, api, guard }), [token, notice, signIn, signOut, api, guard]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
