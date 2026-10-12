import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { describeError } from "../api/errors";
import { Alert } from "../components/Alert";
import { AuthCard } from "../components/AuthCard";
import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { useSession } from "../session/SessionProvider";

const AUTH_FIELDS = { username: "Username", password: "Password" };

export function LoginPage() {
  const { session, signIn } = useSession();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Once signed in, the consent guard decides whether consent is needed first.
  if (session.status === "signed_in") return <Navigate to={from} replace />;

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await signIn(username.trim(), password);
    } catch (failure) {
      setError(
        describeError(failure, {
          fallback: "Sign-in failed. Check your connection and try again.",
          fields: AUTH_FIELDS,
        }),
      );
      setSubmitting(false);
    }
  };

  return (
    <AuthCard
      title="Sign in"
      footer={
        <>
          New here?{" "}
          <Link to="/register" className="font-medium text-accent underline">
            Create an account
          </Link>
        </>
      }
    >
      <form noValidate onSubmit={onSubmit} className="space-y-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <TextField label="Username" value={username} onChange={setUsername} autoComplete="username" required />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          required
        />
        <Button type="submit" disabled={submitting} className="w-full">
          Sign in
        </Button>
      </form>
    </AuthCard>
  );
}
