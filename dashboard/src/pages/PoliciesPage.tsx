import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { Policy } from "../api";
import { useAuth } from "../auth";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import { TextField } from "../components/TextField";

export function PoliciesPage() {
  const { api, guard } = useAuth();
  const [policies, setPolicies] = useState<Policy[]>([]);

  useEffect(() => {
    if (!api) return;
    void guard(() => api.policies()).then((p) => p && setPolicies(p)).catch(() => undefined);
  }, [api, guard]);

  return (
    <div className="space-y-8">
      <PageHeader title="Policies">
        <p>
          Thresholds per application and role. Trust below the moderate threshold asks for a step-up before
          high-risk actions; below the strong threshold, with two or more channels deviating, it asks before
          anything else.
        </p>
      </PageHeader>
      {policies.map((p) => (
        <PolicyForm key={p.policy_id} policy={p} />
      ))}
    </div>
  );
}

function PolicyForm({ policy }: { policy: Policy }) {
  const { api, guard } = useAuth();
  const [high, setHigh] = useState(String(policy.high));
  const [strong, setStrong] = useState(String(policy.strong));
  const [low, setLow] = useState(String(policy.channel_low));
  const [sensitivity, setSensitivity] = useState(policy.action_sensitivity);
  const [exempt, setExempt] = useState(policy.exempt);
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const h = Number(high);
    const s = Number(strong);
    const l = Number(low);
    if (!(h > 0 && h <= 100) || !(s >= 0) || !(l > 0 && l < 1)) {
      setMessage({ tone: "error", text: "Thresholds must be numbers: trust from 0 to 100, channel score between 0 and 1." });
      return;
    }
    if (s >= h) {
      setMessage({ tone: "error", text: "The strong threshold must be lower than the moderate one." });
      return;
    }
    if (!api) return;
    try {
      const saved = await guard(() =>
        api.savePolicy({ ...policy, high: h, strong: s, channel_low: l, action_sensitivity: sensitivity, exempt }),
      );
      if (saved) setMessage({ tone: "success", text: `Policy saved, version ${saved.version}.` });
    } catch (error) {
      setMessage({ tone: "error", text: `The policy was not saved: ${(error as Error).message}` });
    }
  };

  return (
    <form noValidate onSubmit={onSubmit} className="space-y-5 rounded-lg border border-line bg-paper p-6">
      <h2 className="text-lg font-semibold">
        {policy.app_id}, role {policy.role}
      </h2>
      {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
      <div className="grid gap-4 sm:grid-cols-3">
        <TextField label="Moderate below (trust)" inputMode="decimal" value={high} onChange={setHigh} />
        <TextField label="Strong below (trust)" inputMode="decimal" value={strong} onChange={setStrong} />
        <TextField label="Channel score counted as low below" inputMode="decimal" value={low} onChange={setLow} />
      </div>
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">Action sensitivity</legend>
        {Object.entries(sensitivity).map(([action, level]) => (
          <label key={action} className="flex items-center gap-3 text-sm">
            <span className="w-40">{action.replace(/_/g, " ")}</span>
            <select
              value={level}
              onChange={(e) => setSensitivity({ ...sensitivity, [action]: e.target.value })}
              className="rounded-md border border-line-strong bg-paper px-2 py-1"
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </label>
        ))}
      </fieldset>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={exempt} onChange={(e) => setExempt(e.target.checked)} />
        Exempt this role (for example people using assistive input); they are never challenged
      </label>
      <Button type="submit">Save policy</Button>
    </form>
  );
}
