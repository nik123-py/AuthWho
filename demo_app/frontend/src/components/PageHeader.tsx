import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  children?: ReactNode;
}

/** The page's single h1. It can take focus so route changes can move focus to it. */
export function PageHeader({ title, children }: PageHeaderProps) {
  return (
    <header className="mb-8">
      <h1 tabIndex={-1} data-page-title className="text-2xl font-semibold tracking-tight text-ink">
        {title}
      </h1>
      {children ? <div className="mt-2 max-w-prose text-base text-muted">{children}</div> : null}
    </header>
  );
}
