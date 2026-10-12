import { AuthenticatorSetup } from "../components/AuthenticatorSetup";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, CONSENT_VERSION, type Channels, type Consent, type DeclaredDevice } from "../api/client";
import { CONSENT_FIELDS, describeError } from "../api/errors";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { ChannelChoices } from "../components/ChannelChoices";
import { DeviceChoice } from "../components/DeviceChoice";
import { PageHeader } from "../components/PageHeader";
import { ResearchConsentField } from "../components/ResearchConsentField";
import { useCapture } from "../capture/CaptureProvider";
import { useSession } from "../session/SessionProvider";

type Outcome = { tone: "success" | "error"; message: string } | null;

export function SettingsPage() {
  const { session } = useSession();
  if (session.status !== "signed_in" || session.consent === null) return null;
  return (
    <div className="max-w-3xl space-y-12">
      <PageHeader title="Settings">
        <p>Change which signals AuthWho may use, tell it which pointing device you use, or withdraw consent.</p>
      </PageHeader>
      <ChoicesForm consent={session.consent} />
      <AuthenticatorSetup />
      <WithdrawSection />
    </div>
  );
}

function ChoicesForm({ consent }: { consent: Consent }) {
  const { setConsent } = useSession();
  const capture = useCapture();
  const [channels, setChannels] = useState<Channels>(consent.channels);
  const [device, setDevice] = useState<DeclaredDevice>(consent.pointer_device);
  const [research, setResearch] = useState(consent.research_consent);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [saving, setSaving] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setOutcome(null);
    try {
      const stored = await api.giveConsent({
        version: CONSENT_VERSION,
        channels,
        research_consent: research,
        pointer_device: device,
      });
      setConsent(stored);
      // A new stream picks up the new channels and device.
      await capture.restart();
      setOutcome({ tone: "success", message: "Changes saved. Capture now follows your new choices." });
    } catch (error) {
      setOutcome({
        tone: "error",
        message: describeError(error, {
          fallback: "Your changes were not saved. Try again.",
          fields: CONSENT_FIELDS,
        }),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form noValidate onSubmit={onSubmit} className="space-y-8 rounded-lg border border-line bg-paper p-6">
      <h2 className="text-lg font-semibold text-ink">Signals and device</h2>
      {outcome ? <Alert tone={outcome.tone}>{outcome.message}</Alert> : null}
      <ChannelChoices value={channels} onChange={setChannels} />
      <DeviceChoice value={device} onChange={setDevice} />
      <ResearchConsentField checked={research} onChange={setResearch} />
      <Button type="submit" disabled={saving}>
        Save changes
      </Button>
    </form>
  );
}

function WithdrawSection() {
  const { clearConsent } = useSession();
  const capture = useCapture();
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);

  const openConfirmation = () => {
    setConfirming(true);
    requestAnimationFrame(() => confirmRef.current?.focus());
  };

  const cancel = () => {
    setConfirming(false);
    requestAnimationFrame(() => openRef.current?.focus());
  };

  const withdraw = async () => {
    setWorking(true);
    setError(null);
    try {
      await api.withdrawConsent();
      await capture.stop();
      // The consent guard on this page now redirects to the consent page, which confirms the withdrawal.
      clearConsent("withdrawn");
    } catch (failure) {
      // Respect the user's intent locally even if the server did not confirm.
      await capture.stop();
      setError(
        describeError(failure, { fallback: "The server did not confirm the withdrawal. Try again." }),
      );
      setWorking(false);
    }
  };

  return (
    <section className="space-y-4 rounded-lg border border-line bg-paper p-6">
      <h2 className="text-lg font-semibold text-ink">Withdraw consent</h2>
      <p className="max-w-prose text-sm text-ink">
        Withdrawing stops capture at once and deletes your behavioural profile, stored feature vectors and any
        volunteer research data. Your account stays open. To use the app again you are asked for consent again.
      </p>
      {error ? (
        <Alert tone="error" title="Consent was not withdrawn">
          {error} Capture has stopped on this page.
        </Alert>
      ) : null}
      {confirming ? (
        <div className="space-y-3 rounded-md border border-danger bg-danger-soft p-4">
          <p className="text-sm font-medium text-danger-strong">Withdraw consent and delete your behavioural data?</p>
          <div className="flex gap-3">
            <Button ref={confirmRef} variant="danger" onClick={() => void withdraw()} disabled={working}>
              Yes, withdraw consent
            </Button>
            <Button variant="secondary" onClick={cancel} disabled={working}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button ref={openRef} variant="danger" onClick={openConfirmation}>
          Withdraw consent
        </Button>
      )}
    </section>
  );
}
