import { useEffect, useState } from "react";
import type { TrustPoint } from "../api";
import { useAuth } from "../auth";
import { ChannelBreakdown } from "../components/ChannelBreakdown";
import { PageHeader } from "../components/PageHeader";
import { TrustChart } from "../components/TrustChart";
import { LEVEL_LABEL, formatTrust } from "../labels";
import { useLiveFeed } from "../live";

/**
 * Live demo mode (proposal Section 10): follows whichever session changed most recently, so an evaluator
 * can use the demo app in one window and watch trust fall here until step-up is triggered.
 */
export function LiveDemoPage() {
  const { api, guard, token } = useAuth();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [points, setPoints] = useState<TrustPoint[]>([]);
  const [trust, setTrust] = useState<number | null>(null);
  const [scored, setScored] = useState(false);
  const [level, setLevel] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);

  useEffect(() => {
    if (!api || !sessionId) return;
    void guard(() => api.timeline(sessionId)).then((t) => t && setPoints(t)).catch(() => undefined);
  }, [api, guard, sessionId]);

  useLiveFeed(token, (message) => {
    const sid = message.data.session_id;
    if (sid !== sessionId) {
      setSessionId(sid);
      setLevel(null);
      setExplanation(null);
    }
    if (message.type === "trust") {
      const isScored = message.data.state === "scored";
      setScored(isScored);
      setTrust(isScored ? (message.data.trust as number) : null);
      setPoints((current) => (sid === sessionId ? [...current, message.data as unknown as TrustPoint] : current));
    } else {
      setLevel(message.data.level as string);
      setExplanation(message.data.explanation as string);
    }
  });

  const latest = points.at(-1);
  return (
    <div className="space-y-8">
      <PageHeader title="Live demo">
        <p>Use the demo app in another window. This page follows the session that changed most recently.</p>
      </PageHeader>
      {!sessionId ? (
        <p role="status" className="text-sm text-muted">
          Waiting for activity. Sign in to the demo app and start typing.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-10 rounded-lg border border-line bg-paper p-6">
            <div>
              <p className="text-sm text-muted">Trust</p>
              <p className="text-5xl font-semibold tabular-nums" aria-live="polite">
                {formatTrust(scored ? trust : null)}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted">Level</p>
              <p className="text-xl font-medium">{level ? LEVEL_LABEL[level] ?? level : "Not judged yet"}</p>
            </div>
            <div className="min-w-64 flex-1">
              <p className="text-sm text-muted">Latest decision</p>
              <p className="text-base" aria-live="polite">
                {explanation ?? "No decision yet."}
              </p>
            </div>
          </div>
          <TrustChart points={points} showTable={false} />
          <ChannelBreakdown point={latest?.channels ? latest : undefined} />
        </>
      )}
    </div>
  );
}
