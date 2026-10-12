import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import { describeError } from "../api/errors";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import { TextAreaField } from "../components/TextAreaField";

type Outcome = { tone: "success" | "error"; message: string } | null;

export function WritePage() {
  const [text, setText] = useState("");
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [sending, setSending] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) {
      setOutcome({ tone: "error", message: "Write something before sending." });
      return;
    }
    setSending(true);
    setOutcome(null);
    try {
      await api.sendNote(text);
      setText("");
      setOutcome({ tone: "success", message: "Note sent. The text was discarded, not stored." });
    } catch (error) {
      setOutcome({
        tone: "error",
        message: describeError(error, { fallback: "The note was not sent. Try again.", fields: { text: "Your note" } }),
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <PageHeader title="Write">
        <p>
          A short free-writing task. Write naturally for a few minutes; there are no right answers and the text is
          thrown away as soon as you send it.
        </p>
      </PageHeader>

      <form noValidate onSubmit={onSubmit} className="space-y-5 rounded-lg border border-line bg-paper p-6">
        <blockquote className="border-l-4 border-accent pl-4 text-base text-ink">
          Describe a place you know well, such as a street, a room or a park, as if to someone who has never been
          there.
        </blockquote>
        {outcome ? <Alert tone={outcome.tone}>{outcome.message}</Alert> : null}
        <TextAreaField label="Your note" value={text} onChange={setText} rows={10} spellCheck />
        <Button type="submit" disabled={sending}>
          Send note
        </Button>
      </form>
    </div>
  );
}
