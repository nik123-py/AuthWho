import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, CONSENT_VERSION, type Channels, type DeclaredDevice } from "../api/client";
import { CONSENT_FIELDS, describeError } from "../api/errors";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { ChannelChoices } from "../components/ChannelChoices";
import { CheckboxField } from "../components/CheckboxField";
import { CollectionNotice } from "../components/CollectionNotice";
import { DeviceChoice } from "../components/DeviceChoice";
import { PageHeader } from "../components/PageHeader";
import { ResearchConsentField } from "../components/ResearchConsentField";
import { useSession } from "../session/SessionProvider";

const ALL_CHANNELS_ON: Channels = { keystroke: true, pointer: true, interaction: true };

export function ConsentPage() {
  const { session, setConsent } = useSession();
  const navigate = useNavigate();
  const withdrawn = session.status === "signed_in" && session.consentWithdrawn === true;

  const [channels, setChannels] = useState<Channels>(ALL_CHANNELS_ON);
  const [device, setDevice] = useState<DeclaredDevice | null>(null);
  const [research, setResearch] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);

  const showErrors = (messages: string[]) => {
    setErrors(messages);
    requestAnimationFrame(() => errorRef.current?.focus());
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const problems: string[] = [];
    if (device === null) problems.push("Choose mouse or touchpad.");
    if (!agreed) problems.push('Tick "I agree" to give consent.');
    if (problems.length > 0 || device === null) {
      showErrors(problems);
      return;
    }
    setErrors([]);
    setSubmitting(true);
    try {
      const stored = await api.giveConsent({
        version: CONSENT_VERSION,
        channels,
        research_consent: research,
        pointer_device: device,
      });
      setConsent(stored);
      navigate("/", { replace: true });
    } catch (error) {
      showErrors([
        describeError(error, {
          fallback: "Your consent could not be saved. Check your connection and try again.",
          fields: CONSENT_FIELDS,
        }),
      ]);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl">
      <PageHeader title="Consent and enrollment">
        <p>
          AuthWho checks that the person using this account is still you by measuring how you type and move the
          pointer, not what you type. Nothing is captured until you give consent here, and you can change or
          withdraw it at any time in Settings.
        </p>
      </PageHeader>

      {withdrawn ? (
        <div className="mb-8">
          <Alert tone="success" title="Consent withdrawn">
            Your behavioural data has been deleted and capture has stopped. Nothing is captured unless you give
            consent again.
          </Alert>
        </div>
      ) : null}

      <CollectionNotice />

      <form noValidate onSubmit={onSubmit} className="mt-10 space-y-8 rounded-lg border border-line bg-paper p-6">
        {errors.length > 0 ? (
          <Alert ref={errorRef} tone="error" title="Consent was not given">
            <ul className="list-disc pl-5">
              {errors.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </Alert>
        ) : null}

        <ChannelChoices value={channels} onChange={setChannels} />
        <DeviceChoice value={device} onChange={setDevice} invalid={errors.length > 0 && device === null} />

        <ResearchConsentField checked={research} onChange={setResearch} />

        <div className="space-y-4 border-t border-line pt-6">
          <CheckboxField
            name="agree"
            label="I agree to the collection described on this page"
            checked={agreed}
            onChange={setAgreed}
          />
          <Button type="submit" disabled={submitting}>
            Give consent
          </Button>
        </div>
      </form>
    </div>
  );
}
