import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import type { Decision, TrustPoint } from "../api";
import { useAuth } from "../auth";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { ChannelBreakdown } from "../components/ChannelBreakdown";
import { PageHeader } from "../components/PageHeader";
import { TrustChart } from "../components/TrustChart";
import { LEVEL_LABEL, OUTCOME_LABEL, formatTime, formatTrust } from "../labels";
import { useLiveFeed } from "../live";

export function SessionPage() {
  const { sessionId = "" } = useParams();
  const { api, guard, token } = useAuth();
  const [points, setPoints] = useState<TrustPoint[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!api) return;
    try {
      const [t, d] = await Promise.all([
        guard(() => api.timeline(sessionId)),
        guard(() => api.decisions(sessionId)),
      ]);
      if (t) setPoints(t);
      if (d) setDecisions(d);
    } catch {
      setError("This session could not be loaded.");
    }
  }, [api, guard, sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  useLiveFeed(token, (message) => {
    if (message.data.session_id === sessionId) void load();
  });

  const exportReport = async () => {
    if (!api) return;
    const report = await guard(() => api.incidentReport(sessionId));
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `incident-${sessionId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const latest = points.at(-1);
  return (
    <div className="space-y-8">
      <PageHeader title={`Session ${sessionId.slice(0, 8)}`}>
        <p>
          Latest trust: <strong>{formatTrust(latest?.state === "scored" ? latest.trust : null)}</strong>
        </p>
      </PageHeader>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Button variant="secondary" onClick={exportReport}>
        Export incident report
      </Button>
      <TrustChart points={points} decisions={decisions} />
      <ChannelBreakdown point={latest} />
      <section aria-labelledby="decisions-title" className="rounded-lg border border-line bg-paper p-6">
        <h2 id="decisions-title" className="text-lg font-semibold">
          Decisions
        </h2>
        {decisions.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No decisions yet.</p>
        ) : (
          <ol className="mt-4 space-y-4">
            {decisions.map((d) => (
              <li key={d.decision_id} className="border-l-4 border-line-strong pl-4 text-sm">
                <p className="font-medium">
                  {formatTime(d.created_at)}: {LEVEL_LABEL[d.level] ?? d.level}, {OUTCOME_LABEL[d.outcome] ?? d.outcome}
                  {d.action_code ? ` (${d.action_code.replace(/_/g, " ")})` : ""}
                </p>
                <p className="mt-1 text-ink">{d.explanation}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
