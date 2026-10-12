import { useState } from "react";
import type { FormEvent } from "react";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { CheckboxField } from "../components/CheckboxField";
import { PageHeader } from "../components/PageHeader";
import { SelectField } from "../components/SelectField";
import { TextField } from "../components/TextField";

const CONTACT_METHODS = ["Email", "Phone", "Post"] as const;

type Outcome = { tone: "success" | "error"; messages: string[] } | null;

/** A practice form that exists to produce ordinary form-filling behaviour. Nothing is sent. */
export function FormPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [contact, setContact] = useState<string>(CONTACT_METHODS[0]);
  const [summary, setSummary] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>(null);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const missing: string[] = [];
    if (!name.trim()) missing.push("Enter your full name.");
    if (!email.trim()) missing.push("Enter your email address.");
    if (!address.trim()) missing.push("Enter your street address.");
    if (!city.trim()) missing.push("Enter your city.");
    setOutcome(
      missing.length > 0
        ? { tone: "error", messages: missing }
        : { tone: "success", messages: ["Your details look complete. This practice form is not sent anywhere."] },
    );
  };

  return (
    <div className="max-w-2xl">
      <PageHeader title="Your details">
        <p>A practice form. Fill it in as you would any contact form; nothing you enter leaves this page.</p>
      </PageHeader>

      <form noValidate onSubmit={onSubmit} className="space-y-5 rounded-lg border border-line bg-paper p-6">
        {outcome ? (
          <Alert tone={outcome.tone}>
            {outcome.messages.length === 1 ? (
              outcome.messages[0]
            ) : (
              <ul className="list-disc pl-5">
                {outcome.messages.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
          </Alert>
        ) : null}
        <TextField label="Full name" value={name} onChange={setName} autoComplete="name" required />
        <TextField
          label="Email address"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          required
        />
        <TextField
          label="Street address"
          value={address}
          onChange={setAddress}
          autoComplete="street-address"
          required
        />
        <TextField label="City" value={city} onChange={setCity} autoComplete="address-level2" required />
        <SelectField
          label="Preferred contact method"
          value={contact}
          options={CONTACT_METHODS}
          onChange={setContact}
        />
        <CheckboxField label="Send me a monthly summary by email" checked={summary} onChange={setSummary} />
        <Button type="submit">Check details</Button>
      </form>
    </div>
  );
}
