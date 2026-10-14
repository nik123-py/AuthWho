import { useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "../auth";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import { TextField } from "../components/TextField";

export function SignInPage() {
  const { signIn, notice } = useAuth();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!token.trim()) {
      setError("Enter the admin token.");
      return;
    }
    signIn(token.trim());
  };

  return (
    <div className="max-w-md">
      <PageHeader title="Administrator sign in">
        <p>Enter the admin token configured for this AuthWho server. It is kept only for this browser tab.</p>
      </PageHeader>
      <form noValidate onSubmit={onSubmit} className="space-y-5 rounded-lg border border-line bg-paper p-6">
        {notice || error ? <Alert tone="error">{error ?? notice}</Alert> : null}
        <TextField label="Admin token" type="password" autoComplete="off" value={token} onChange={setToken} required />
        <Button type="submit" className="w-full">
          Sign in
        </Button>
      </form>
    </div>
  );
}
