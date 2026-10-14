import type { ReactNode, Ref } from "react";

type Tone = "error" | "success" | "info";

const TONES: Record<Tone, string> = {
  error: "border-danger bg-danger-soft text-danger-strong",
  success: "border-success bg-success-soft text-success-strong",
  info: "border-line-strong bg-canvas text-ink",
};

interface AlertProps {
  tone: Tone;
  title?: string;
  children: ReactNode;
  ref?: Ref<HTMLDivElement>;
}

/**
 * Errors use role="alert" so they are announced at once; confirmations use role="status".
 * The element can take focus programmatically so a form can move focus to its error summary.
 */
export function Alert({ tone, title, children, ref }: AlertProps) {
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-md border-l-4 px-4 py-3 text-sm ${TONES[tone]}`}
    >
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={title ? "mt-1" : undefined}>{children}</div>
    </div>
  );
}
