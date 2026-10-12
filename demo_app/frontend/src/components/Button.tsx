import type { ComponentPropsWithRef } from "react";

type Variant = "primary" | "secondary" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-strong border-accent",
  secondary: "bg-paper text-ink hover:bg-canvas border-line-strong",
  danger: "bg-danger text-white hover:bg-danger-strong border-danger",
};

interface ButtonProps extends ComponentPropsWithRef<"button"> {
  variant?: Variant;
}

export function Button({ variant = "primary", type = "button", className = "", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center rounded-md border px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60 ${VARIANTS[variant]} ${className}`}
      {...rest}
    />
  );
}
