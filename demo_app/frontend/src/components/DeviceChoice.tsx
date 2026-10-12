import { useId } from "react";
import type { DeclaredDevice } from "../api/client";

const OPTIONS: { value: DeclaredDevice; label: string }[] = [
  { value: "mouse", label: "Mouse" },
  { value: "touchpad", label: "Touchpad" },
];

interface DeviceChoiceProps {
  value: DeclaredDevice | null;
  onChange: (value: DeclaredDevice) => void;
  invalid?: boolean;
}

/** Browsers report mice and touchpads alike, so the user declares the device. */
export function DeviceChoice({ value, onChange, invalid = false }: DeviceChoiceProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <fieldset className="space-y-3" aria-describedby={hintId} aria-invalid={invalid || undefined}>
      <legend className="text-base font-semibold text-ink">Which pointing device are you using?</legend>
      <p id={hintId} className="text-sm text-muted">
        Required. Mice and touchpads move differently, so each has its own profile. You can change this later
        in Settings.
      </p>
      <div className="flex gap-6">
        {OPTIONS.map((option) => {
          const optionId = `${id}-${option.value}`;
          return (
            <div key={option.value} className="flex items-center gap-2">
              <input
                id={optionId}
                type="radio"
                name={`${id}-device`}
                value={option.value}
                checked={value === option.value}
                onChange={() => onChange(option.value)}
                className="size-4 accent-accent"
              />
              <label htmlFor={optionId} className="text-sm font-medium text-ink">
                {option.label}
              </label>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
