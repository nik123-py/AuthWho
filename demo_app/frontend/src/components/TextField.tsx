import { useId } from "react";
import type { InputHTMLAttributes } from "react";

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "id"> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
}

export function TextField({ label, value, onChange, hint, type = "text", className = "", ...rest }: TextFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="text-sm text-muted">
          {hint}
        </p>
      ) : null}
      <input
        id={id}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={hint ? hintId : undefined}
        className="rounded-md border border-line-strong bg-paper px-3 py-2 text-sm text-ink"
        {...rest}
      />
    </div>
  );
}
