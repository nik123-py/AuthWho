import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import { describeError } from "../api/errors";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import { TextField } from "../components/TextField";
import { useCapture } from "../capture/CaptureProvider";

type Outcome = { tone: "success" | "error"; message: string } | null;

export function PayeesPage() {
  const { markAction } = useCapture();
  const [name, setName] = useState("");
  const [account, setAccount] = useState("");
  const [payees, setPayees] = useState<string[]>([]);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || !account.trim()) {
      setOutcome({ tone: "error", message: "Enter both the payee name and the account number." });
      return;
    }
    setSubmitting(true);
    setOutcome(null);
    // Mark the sensitive action for AuthWho immediately before the request.
    markAction("add_payee");
    try {
      await api.addPayee(name.trim(), account.trim());
      setPayees((current) => [...current, name.trim()]);
      setOutcome({ tone: "success", message: `Payee added. ${name.trim()} is now in your payee list.` });
      setName("");
      setAccount("");
    } catch (error) {
      setOutcome({
        tone: "error",
        message: describeError(error, {
          fallback: "The payee was not added. Try again.",
          fields: { name: "Payee name", account: "Account number" },
        }),
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <PageHeader title="Payees">
        <p>Adding a payee is a high-risk action. You may be asked to confirm it is you.</p>
      </PageHeader>

      <form noValidate onSubmit={onSubmit} className="space-y-5 rounded-lg border border-line bg-paper p-6">
        <h2 className="text-lg font-semibold text-ink">Add a payee</h2>
        {outcome ? <Alert tone={outcome.tone}>{outcome.message}</Alert> : null}
        <TextField label="Payee name" value={name} onChange={setName} autoComplete="off" required />
        <TextField
          label="Account number"
          value={account}
          onChange={setAccount}
          inputMode="numeric"
          autoComplete="off"
          required
        />
        <Button type="submit" disabled={submitting}>
          Add payee
        </Button>
      </form>

      <section className="mt-10">
        <h2 className="text-lg font-semibold text-ink">Your payees</h2>
        {payees.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No payees added yet. Use the form above to add one.</p>
        ) : (
          <ul className="mt-3 divide-y divide-line rounded-lg border border-line bg-paper">
            {payees.map((payee, index) => (
              <li key={`${payee}-${index}`} className="px-4 py-3 text-sm text-ink">
                {payee}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
