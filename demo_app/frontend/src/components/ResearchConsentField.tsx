import { CheckboxField } from "./CheckboxField";

interface ResearchConsentFieldProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

/** Research use is a separate, optional consent from the authentication checks. */
export function ResearchConsentField({ checked, onChange }: ResearchConsentFieldProps) {
  return (
    <fieldset className="space-y-3">
      <legend className="text-base font-semibold text-ink">Research use</legend>
      <CheckboxField
        name="research-consent"
        label="Add my timing data to the volunteer research dataset"
        description="Optional and separate from the checks above. Stored encrypted under a pseudonymous ID and deleted when the project ends."
        checked={checked}
        onChange={onChange}
      />
    </fieldset>
  );
}
