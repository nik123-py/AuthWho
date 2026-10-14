import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { SessionRow } from "../api";
import { useAuth } from "../auth";
import { Alert } from "../components/Alert";
import { PageHeader } from "../components/PageHeader";
import { LEVEL_LABEL, STATUS_LABEL, formatTime, formatTrust } from "../labels";
import { useLiveFeed } from "../live";

export function SessionsPage() {
  const { api, guard, token } = useAuth();
  const [rows, setRows] = useState<SessionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!api) return;
    try {
      const data = await guard(() => api.sessions());
      if (data) setRows(data);
    } catch {
      setError("Sessions could not be loaded. Check that the AuthWho API is running.");
    }
  }, [api, guard]);

  useEffect(() => {
    void load();
  }, [load]);

  useLiveFeed(token, (message) => {
    const sid = message.data.session_id;
    setRows((current) => {
      if (!current) return current;
      if (!current.some((r) => r.session_id === sid)) {
        void load();
        return current;
      }
      return current.map((r) => {
        if (r.session_id !== sid) return r;
        if (message.type === "trust") {
          return { ...r, trust: (message.data.trust as number | null) ?? null, state: message.data.state as string };
        }
        const outcome = message.data.outcome as string;
        return {
          ...r,
          level: message.data.level as SessionRow["level"],
          status: outcome === "terminate" ? "terminated" : outcome === "step_up" ? "step_up_required" : r.status,
        };
      });
    });
  });

  return (
    <div>
      <PageHeader title="Sessions">
        <p>Live trust for every session. Trust updates arrive as people type and move the mouse.</p>
      </PageHeader>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {rows === null && !error ? <p role="status" className="text-sm text-muted">Loading</p> : null}
      {rows && rows.length === 0 ? (
        <p className="text-sm text-muted">No sessions yet. Sign in to the demo app to start one.</p>
      ) : null}
      {rows && rows.length > 0 ? (
        <table className="w-full overflow-hidden rounded-lg border border-line bg-paper text-left text-sm">
          <caption className="sr-only">Sessions</caption>
          <thead className="bg-canvas text-muted">
            <tr>
              <th scope="col" className="px-4 py-3">Session</th>
              <th scope="col" className="px-4 py-3">Started</th>
              <th scope="col" className="px-4 py-3">Status</th>
              <th scope="col" className="px-4 py-3">Trust</th>
              <th scope="col" className="px-4 py-3">Level</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => (
              <tr key={r.session_id}>
                <td className="px-4 py-3">
                  <Link to={`/sessions/${r.session_id}`} className="font-mono text-accent underline">
                    {r.session_id.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-4 py-3">{formatTime(r.created_at)}</td>
                <td className="px-4 py-3">{STATUS_LABEL[r.status] ?? r.status}</td>
                <td className="px-4 py-3 font-semibold">{formatTrust(r.state === "scored" ? r.trust : null)}</td>
                <td className="px-4 py-3">{r.level ? LEVEL_LABEL[r.level] : "Cannot determine"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
