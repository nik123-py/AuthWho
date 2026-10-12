import { useId } from "react";
import type { ReactNode } from "react";

interface CheckboxFieldProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: ReactNode;
  name?: string;
}

export function CheckboxField({ label, checked, onChange, description, name }: CheckboxFieldProps) {
  const id = useId();
  const descriptionId = `${id}-description`;
  return (
    <div className="flex items-start gap-3">
      <input
        id={id}
        name={name}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        aria-describedby={description ? descriptionId : undefined}
        className="mt-0.5 size-4 shrink-0 accent-accent"
      />
      <div className="text-sm">
        <label htmlFor={id} className="font-medium text-ink">
          {label}
        </label>
        {description ? (
          <p id={descriptionId} className="mt-0.5 text-muted">
            {description}
          </p>
        ) : null}
      </div>
    </div>
  );
}
