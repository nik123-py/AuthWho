import { useId } from "react";
import type { TextareaHTMLAttributes } from "react";

interface TextAreaFieldProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "id"> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
}

export function TextAreaField({ label, value, onChange, hint, rows = 8, ...rest }: TextAreaFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {hint ? (
        <p id={hintId} className="text-sm text-muted">
          {hint}
        </p>
      ) : null}
      <textarea
        id={id}
        rows={rows}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={hint ? hintId : undefined}
        className="rounded-md border border-line-strong bg-paper px-3 py-2 text-base leading-relaxed text-ink"
        {...rest}
      />
    </div>
  );
}
