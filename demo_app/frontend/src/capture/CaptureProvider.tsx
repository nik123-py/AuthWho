import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useSession } from "../session/SessionProvider";
import { CaptureController } from "./CaptureController";

/** Route path to page key in GET /api/registry. Pages without a key are never reported. */
const PAGE_KEYS: Record<string, string> = {
  "/": "home",
  "/write": "write",
  "/form": "form",
  "/payees": "payees",
  "/reports": "reports",
  "/what-we-collect": "collect",
  "/settings": "settings",
};

export type ActionKey = "add_payee" | "export_report";

interface CaptureContextValue {
  /** Call immediately before sending a sensitive request. */
  markAction: (action: ActionKey) => void;
  /** Flushes and stops capture, for sign-out and consent withdrawal. */
  stop: () => Promise<void>;
  /** Stops and starts again with a fresh stream, after the user changes channel or device choices. */
  restart: () => Promise<void>;
}

const CaptureContext = createContext<CaptureContextValue | null>(null);

export function CaptureProvider({ children }: { children: ReactNode }) {
  const [controller] = useState(() => new CaptureController());
  const { session, clearConsent } = useSession();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [runs, setRuns] = useState(0);

  const consented = session.status === "signed_in" && session.consent !== null;

  const begin = useCallback(async () => {
    try {
      const result = await controller.ensureStarted();
      if (result === "no_consent") {
        clearConsent("missing");
        navigate("/consent", { replace: true });
      }
    } catch {
      // Capture is best effort. The app keeps working under normal session rules without it.
    }
  }, [controller, clearConsent, navigate]);

  useEffect(() => {
    if (consented) void begin();
    else void controller.stop();
  }, [consented, begin, controller, runs]);

  useEffect(() => {
    controller.setPage(PAGE_KEYS[pathname] ?? null);
  }, [controller, pathname]);

  const value = useMemo<CaptureContextValue>(
    () => ({
      markAction: (action) => controller.markAction(action),
      stop: () => controller.stop(),
      restart: async () => {
        await controller.stop();
        setRuns((n) => n + 1);
      },
    }),
    [controller],
  );

  return <CaptureContext.Provider value={value}>{children}</CaptureContext.Provider>;
}

export function useCapture(): CaptureContextValue {
  const value = useContext(CaptureContext);
  if (!value) throw new Error("useCapture must be used inside CaptureProvider");
  return value;
}
