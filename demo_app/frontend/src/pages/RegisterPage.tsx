import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api/client";
import { describeError } from "../api/errors";
import { Alert } from "../components/Alert";
import { AuthCard } from "../components/AuthCard";
import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { useSession } from "../session/SessionProvider";

const AUTH_FIELDS = { username: "Username", password: "Password" };
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 1024;

export function RegisterPage() {
  const { session, signIn } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // A new account has no consent yet, so the consent guard sends the user to the consent page.
  if (session.status === "signed_in") return <Navigate to="/" replace />;

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("Choose a username and a password.");
      return;
    }
    if (password.length < PASSWORD_MIN) {
      setError(`Use a password of at least ${PASSWORD_MIN} characters.`);
      return;
    }
    if (password.length > PASSWORD_MAX) {
      setError(`Use a password of at most ${PASSWORD_MAX} characters.`);
      return;
    }
    if (password !== confirm) {
      setError("The passwords do not match.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await api.register(username.trim(), password);
      await signIn(username.trim(), password);
    } catch (failure) {
      setError(
        describeError(failure, {
          fallback: "The account was not created. Check your connection and try again.",
          fields: AUTH_FIELDS,
        }),
      );
      setSubmitting(false);
    }
  };

  return (
    <AuthCard
      title="Create an account"
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-accent underline">
            Sign in
          </Link>
        </>
      }
    >
      <form noValidate onSubmit={onSubmit} className="space-y-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <TextField
          label="Username"
          hint="Capital letters do not matter: Asha and asha are the same username."
          value={username}
          onChange={setUsername}
          autoComplete="username"
          required
        />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          hint={`At least ${PASSWORD_MIN} characters.`}
          required
        />
        <TextField
          label="Confirm password"
          type="password"
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
          required
        />
        <Button type="submit" disabled={submitting} className="w-full">
          Create account
        </Button>
      </form>
    </AuthCard>
  );
}
