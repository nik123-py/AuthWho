import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError, SESSION_ENDED_EVENT, STEP_UP_EVENT, api, type StepUpMethod } from "../api/client";
import { describeError } from "../api/errors";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { useCapture } from "../capture/CaptureProvider";
import { useSession } from "./SessionProvider";

/** How often the app asks whether AuthWho wants the user to confirm it is them. */
export const STATUS_POLL_MS = 5000;

/**
 * Shows the "Confirm it is you" dialog when AuthWho asks for a step-up, either because a request was
 * answered with step_up_required or because the session status says so, and sends the user to the
 * session-ended page when AuthWho ends the session. It never shows scores or reasons: the internal
 * trust score is for administrators only.
 */
export function StepUpGuard() {
  const { session, markEnded } = useSession();
  const capture = useCapture();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [method, setMethod] = useState<StepUpMethod | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [ending, setEnding] = useState(false);

  const consented = session.status === "signed_in" && session.consent !== null;

  const ended = useCallback(async () => {
    setMethod(null);
    await capture.stop();
    // The router navigates in a transition; the session is marked ended only once the
    // session-ended page is showing (effect below), so page guards do not redirect to sign-in first.
    setEnding(true);
    navigate("/session-ended", { replace: true });
  }, [capture, navigate]);

  useEffect(() => {
    if (ending && pathname === "/session-ended") {
      setEnding(false);
      markEnded();
    }
  }, [ending, pathname, markEnded]);

  useEffect(() => {
    const onStepUp = (event: Event) => {
      setConfirmed(false);
      setMethod((event as CustomEvent<{ method: StepUpMethod }>).detail.method);
    };
    const onEnded = () => void ended();
    window.addEventListener(STEP_UP_EVENT, onStepUp);
    window.addEventListener(SESSION_ENDED_EVENT, onEnded);
    return () => {
      window.removeEventListener(STEP_UP_EVENT, onStepUp);
      window.removeEventListener(SESSION_ENDED_EVENT, onEnded);
    };
  }, [ended]);

  useEffect(() => {
    if (!consented) return;
    let cancelled = false;
    const check = async () => {
      try {
        const state = await api.session();
        if (!cancelled && state.status === "step_up_required") {
          setConfirmed(false);
          setMethod(state.method);
        }
      } catch {
        // A failed status check changes nothing; session_ended is handled by the event above.
      }
    };
    void check();
    const timer = window.setInterval(check, STATUS_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [consented]);

  return (
    <>
      {confirmed ? (
        <div className="fixed bottom-6 right-6 z-20 max-w-sm">
          <Alert tone="success">Thanks, you confirmed it is you. Try your action again.</Alert>
        </div>
      ) : null}
      {method ? (
        <StepUpDialog
          method={method}
          onPassed={() => {
            setMethod(null);
            setConfirmed(true);
          }}
          onEnded={() => void ended()}
        />
      ) : null}
    </>
  );
}

interface DialogProps {
  method: StepUpMethod;
  onPassed: () => void;
  onEnded: () => void;
}

function StepUpDialog({ method, onPassed, onEnded }: DialogProps) {
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const label = method === "totp" ? "Authenticator code" : "Password";

  useEffect(() => {
    heading.current?.focus();
  }, []);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!answer) {
      setError(`Enter your ${label.toLowerCase()}.`);
      return;
    }
    setSending(true);
    setError(null);
    try {
      await api.stepUp(method === "totp" ? { code: answer.trim() } : { password: answer });
      onPassed();
    } catch (err) {
      if (err instanceof ApiError && err.code === "step_up_failed") {
        const left = (err.body as { attempts_left?: number }).attempts_left ?? 0;
        setError(`That was not right. ${left} ${left === 1 ? "attempt" : "attempts"} left.`);
        setAnswer("");
      } else if (err instanceof ApiError && (err.code === "session_ended" || err.status === 401)) {
        onEnded();
      } else {
        setError(describeError(err, { fallback: "The check could not be completed. Try again." }));
      }
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-ink/40 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="step-up-title"
        className="w-full max-w-md rounded-lg border border-line bg-paper p-6 shadow-lg"
      >
        <h2 id="step-up-title" ref={heading} tabIndex={-1} className="text-lg font-semibold text-ink">
          Confirm it is you
        </h2>
        <p className="mt-2 text-sm text-muted">
          {method === "totp"
            ? "Enter the 6-digit code from your authenticator app to continue."
            : "Enter your password to continue."}{" "}
          This is a routine check. AuthWho never shows any score here.
        </p>
        <form noValidate onSubmit={onSubmit} className="mt-5 space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <TextField
            label={label}
            type={method === "totp" ? "text" : "password"}
            inputMode={method === "totp" ? "numeric" : undefined}
            autoComplete={method === "totp" ? "one-time-code" : "current-password"}
            value={answer}
            onChange={setAnswer}
            required
          />
          <Button type="submit" disabled={sending}>
            Confirm
          </Button>
        </form>
      </div>
    </div>
  );
}
