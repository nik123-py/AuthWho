import { useId } from "react";
import { COLLECTED, NEVER_COLLECTED, RETENTION, STRONGEST_ACTION } from "../content/collection";

interface CollectionNoticeProps {
  /** Heading level for the notice's section headings, so it fits the page outline. */
  headingLevel?: 2 | 3;
  /** Section titles. The defaults suit a page whose own title is not "What we collect". */
  collectedTitle?: string;
  neverTitle?: string;
}

export function CollectionNotice({
  headingLevel = 2,
  collectedTitle = "What we collect",
  neverTitle = "What we never collect",
}: CollectionNoticeProps) {
  const retentionId = useId();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const headingClass = "text-lg font-semibold text-ink";
  return (
    <div className="space-y-8">
      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-lg border border-line bg-paper p-5">
          <Heading className={headingClass}>{collectedTitle}</Heading>
          <p className="mt-1 text-sm text-muted">
            Only after you give consent, and only for the channels you have not opted out of.
          </p>
          <ul aria-label="Signals collected only after consent" className="mt-4 list-disc space-y-2 pl-5 text-sm text-ink">
            {COLLECTED.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
        <section className="rounded-lg border border-line bg-paper p-5">
          <Heading className={headingClass}>{neverTitle}</Heading>
          <p className="mt-1 text-sm text-muted">Not in any channel, and not with any setting.</p>
          <ul aria-label="Never collected" className="mt-4 list-disc space-y-2 pl-5 text-sm text-ink">
            {NEVER_COLLECTED.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </div>

      <section>
        <Heading id={retentionId} className={headingClass}>
          How long data is kept
        </Heading>
        <table className="mt-3 w-full border-collapse text-left text-sm" aria-labelledby={retentionId}>
          <thead>
            <tr className="border-b border-line-strong text-ink">
              <th scope="col" className="py-2 pr-4 font-semibold">
                Data
              </th>
              <th scope="col" className="py-2 pr-4 font-semibold">
                Where
              </th>
              <th scope="col" className="py-2 font-semibold">
                How long
              </th>
            </tr>
          </thead>
          <tbody>
            {RETENTION.map((row) => (
              <tr key={row.data} className="border-b border-line align-top">
                <th scope="row" className="py-2 pr-4 font-medium text-ink">
                  {row.data}
                </th>
                <td className="py-2 pr-4 text-muted">{row.where}</td>
                <td className="py-2 text-ink">{row.howLong}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-4 max-w-prose text-sm text-ink">{STRONGEST_ACTION}</p>
      </section>
    </div>
  );
}
