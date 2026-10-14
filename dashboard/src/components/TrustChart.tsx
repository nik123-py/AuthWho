import { useEffect, useRef } from "react";
import type { Decision, TrustPoint } from "../api";
import { formatTime, formatTrust } from "../labels";

interface Props {
  points: TrustPoint[];
  decisions?: Decision[];
  /** The data table is the accessible equivalent of the chart. */
  showTable?: boolean;
}

/**
 * Trust over time (Chart.js line) with decision points marked and the moderate (75) and strong (50)
 * thresholds drawn. Insufficient-signal points leave a gap instead of a guessed value.
 */
export function TrustChart({ points, decisions = [], showTable = true }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = canvas.current;
    if (!el || !el.getContext) return;
    let chart: { destroy: () => void } | null = null;
    let cancelled = false;
    void import("chart.js/auto").then(({ default: Chart }) => {
      if (cancelled) return;
      const labels = points.map((p) => formatTime(p.at));
      const decisionTimes = new Set(decisions.map((d) => formatTime(d.created_at)));
      try {
        chart = new Chart(el, {
          type: "line",
          data: {
            labels,
            datasets: [
              { label: "Trust", data: points.map((p) => p.trust), borderColor: "#0b5563", spanGaps: false, tension: 0.2 },
              {
                label: "Decision",
                data: points.map((p) => (decisionTimes.has(formatTime(p.at)) ? p.trust : null)),
                borderColor: "#a1262b",
                backgroundColor: "#a1262b",
                showLine: false,
                pointRadius: 6,
              },
              { label: "Moderate threshold", data: points.map(() => 75), borderColor: "#b45309", borderDash: [6, 4], pointRadius: 0 },
              { label: "Strong threshold", data: points.map(() => 50), borderColor: "#7a1c20", borderDash: [2, 4], pointRadius: 0 },
            ],
          },
          options: { animation: false, scales: { y: { min: 0, max: 100 } }, maintainAspectRatio: false },
        });
      } catch {
        // No canvas support: the data table below still carries the same information.
      }
    });
    return () => {
      cancelled = true;
      chart?.destroy();
    };
  }, [points, decisions]);

  return (
    <div>
      <div className="h-72 rounded-lg border border-line bg-paper p-4">
        <canvas ref={canvas} role="img" aria-label="Trust over time chart. The same values are in the table that follows." />
      </div>
      {showTable ? (
        <table className="sr-only">
          <caption>Trust over time</caption>
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">Trust</th>
              <th scope="col">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.seq}>
                <td>{formatTime(p.at)}</td>
                <td>{formatTrust(p.trust)}</td>
                <td>{p.confidence === null ? "None" : p.confidence.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
