import type { ReactNode } from "react";
import { PageHeader } from "./PageHeader";

interface AuthCardProps {
  title: string;
  children: ReactNode;
  footer: ReactNode;
}

/** A narrow, centred panel for the sign-in and account creation forms. */
export function AuthCard({ title, children, footer }: AuthCardProps) {
  return (
    <div className="mx-auto mt-6 w-full max-w-sm">
      <div className="rounded-lg border border-line bg-paper p-8">
        <PageHeader title={title} />
        {children}
      </div>
      <p className="mt-4 text-center text-sm text-muted">{footer}</p>
    </div>
  );
}
