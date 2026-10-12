import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import { describeError } from "../api/errors";
import { useSession } from "../session/SessionProvider";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { TextField } from "./TextField";

/**
 * Optional authenticator app (TOTP) for step-up checks. Without one, a step-up asks for the password.
 * The key is shown once as text to type into any authenticator app; no QR library is needed.
 */
export function AuthenticatorSetup() {
  const { session, refresh } = useSession();
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const enabled = session.status === "signed_in" && session.totpEnabled;

  const begin = async () => {
    setError(null);
    try {
      setSecret((await api.totpSetup()).secret);
    } catch (err) {
      setError(describeError(err, { fallback: "Setup could not start. Try again." }));
    }
  };

  const confirm = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await api.totpConfirm(code.trim());
      setSecret(null);
      await refresh();
    } catch (err) {
      setError(describeError(err, { fallback: "The code could not be checked. Try again." }));
    }
  };

  return (
    <section className="space-y-4 rounded-lg border border-line bg-paper p-6">
      <h2 className="text-lg font-semibold text-ink">Authenticator app</h2>
      {enabled ? (
        <p className="text-sm text-ink">Your authenticator app is set up. Identity checks will ask for its code.</p>
      ) : secret === null ? (
        <>
          <p className="text-sm text-muted">
            If AuthWho is unsure it is you, it asks you to confirm before a sensitive action. Without an
            authenticator app, it asks for your password.
          </p>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Button type="button" onClick={begin}>
            Set up an authenticator app
          </Button>
        </>
      ) : (
        <form noValidate onSubmit={confirm} className="space-y-4">
          <p className="text-sm text-ink">
            Add a new account in your authenticator app and enter this key:{" "}
            <code className="rounded bg-canvas px-2 py-1 font-mono text-sm">{secret}</code>
          </p>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <TextField
            label="Code from your authenticator app"
            value={code}
            onChange={setCode}
            inputMode="numeric"
            autoComplete="one-time-code"
            required
          />
          <Button type="submit">Confirm code</Button>
        </form>
      )}
    </section>
  );
}
