import { useState } from "react";
import { api } from "../api/client";
import { describeError } from "../api/errors";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import { useCapture } from "../capture/CaptureProvider";

const REPORTS = [
  { title: "Account statement", period: "September 2026", size: "4 pages" },
  { title: "Account statement", period: "August 2026", size: "5 pages" },
  { title: "Transaction history", period: "July to September 2026", size: "12 pages" },
  { title: "Payee activity", period: "July to September 2026", size: "2 pages" },
];

type Outcome = { tone: "success" | "error"; message: string } | null;

export function ReportsPage() {
  const { markAction } = useCapture();
  const [outcome, setOutcome] = useState<Outcome>(null);
  const [exporting, setExporting] = useState(false);

  const onExport = async () => {
    setExporting(true);
    setOutcome(null);
    // Mark the sensitive action for AuthWho immediately before the request.
    markAction("export_report");
    try {
      await api.exportReports();
      setOutcome({ tone: "success", message: "Export started. The reports are being prepared." });
    } catch (error) {
      setOutcome({
        tone: "error",
        message: describeError(error, { fallback: "The export did not start. Try again." }),
      });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="max-w-3xl">
      <PageHeader title="Reports">
        <p>Exporting reports is a high-risk action. You may be asked to confirm it is you.</p>
      </PageHeader>

      <table className="w-full border-collapse rounded-lg bg-paper text-left text-sm" aria-label="Available reports">
        <thead>
          <tr className="border-b border-line-strong">
            <th scope="col" className="px-4 py-2 font-semibold">
              Report
            </th>
            <th scope="col" className="px-4 py-2 font-semibold">
              Period
            </th>
            <th scope="col" className="px-4 py-2 font-semibold">
              Length
            </th>
          </tr>
        </thead>
        <tbody>
          {REPORTS.map((report) => (
            <tr key={`${report.title}-${report.period}`} className="border-b border-line">
              <th scope="row" className="px-4 py-3 font-medium text-ink">
                {report.title}
              </th>
              <td className="px-4 py-3 text-muted">{report.period}</td>
              <td className="px-4 py-3 text-muted">{report.size}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-6 flex items-center gap-4">
        <Button onClick={() => void onExport()} disabled={exporting}>
          Export reports
        </Button>
      </div>
      {outcome ? (
        <div className="mt-4">
          <Alert tone={outcome.tone}>{outcome.message}</Alert>
        </div>
      ) : null}
    </div>
  );
}
