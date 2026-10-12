import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "../session/SessionProvider";

function Loading() {
  return (
    <p role="status" className="text-sm text-muted">
      Loading
    </p>
  );
}

/** Pages that need a signed-in user. */
export function RequireSignIn({ children }: { children: ReactNode }) {
  const { session } = useSession();
  const location = useLocation();
  if (session.status === "loading") return <Loading />;
  if (session.status === "signed_out") return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

/** Pages that need a signed-in user who has given consent. */
export function RequireConsent({ children }: { children: ReactNode }) {
  const { session } = useSession();
  const location = useLocation();
  if (session.status === "loading") return <Loading />;
  if (session.status === "signed_out") return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (session.consent === null) return <Navigate to="/consent" replace />;
  return <>{children}</>;
}
