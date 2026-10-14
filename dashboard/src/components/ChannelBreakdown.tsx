import type { TrustPoint } from "../api";
import { CHANNEL_LABEL, CHANNEL_STATUS_LABEL, behaviour } from "../labels";

const ORDER = ["keystroke", "pointer", "interaction"];

/** Per-channel contribution at the latest trust point: status, score and the behaviour that moved most. */
export function ChannelBreakdown({ point }: { point: TrustPoint | undefined }) {
  return (
    <section aria-labelledby="channels-title" className="rounded-lg border border-line bg-paper p-6">
      <h2 id="channels-title" className="text-lg font-semibold">
        Channel breakdown
      </h2>
      {!point ? (
        <p className="mt-2 text-sm text-muted">No scored activity yet.</p>
      ) : (
        <ul className="mt-4 divide-y divide-line">
          {ORDER.map((name) => {
            const c = point.channels?.[name];
            if (!c) return null;
            const scored = c.status === "scored" && c.score !== null;
            const status = scored ? (c.score! < 0.5 ? "Deviates" : "Matches") : CHANNEL_STATUS_LABEL[c.status] ?? c.status;
            const top = c.top_features?.[0];
            return (
              <li key={name} className="flex flex-wrap items-baseline justify-between gap-2 py-3 text-sm">
                <span className="font-medium">{CHANNEL_LABEL[name] ?? name}</span>
                <span className={scored && c.score! < 0.5 ? "font-semibold text-danger-strong" : "text-muted"}>
                  {status}
                  {scored ? ` (match ${c.score!.toFixed(2)})` : ""}
                </span>
                {scored && top ? (
                  <span className="w-full text-muted">Main deviation: {behaviour(top.name)}</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
