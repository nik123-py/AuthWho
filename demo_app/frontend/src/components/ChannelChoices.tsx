import type { ChannelName, Channels } from "../api/client";
import { CheckboxField } from "./CheckboxField";

const CHANNELS: { name: ChannelName; label: string; description: string }[] = [
  {
    name: "keystroke",
    label: "Typing rhythm",
    description:
      "When each key goes down and comes up, with a coarse category such as letter or digit. Never which key or character.",
  },
  {
    name: "pointer",
    label: "Pointer movement",
    description: "Where the pointer moves, when, and when you click.",
  },
  {
    name: "interaction",
    label: "Page interaction",
    description:
      "Wheel and scroll movement, which form field has focus (by position, not by name), page changes, whether copy, cut or paste happened, and whether this tab is visible.",
  },
];

interface ChannelChoicesProps {
  value: Channels;
  onChange: (value: Channels) => void;
}

export function ChannelChoices({ value, onChange }: ChannelChoicesProps) {
  return (
    <fieldset className="space-y-4">
      <legend className="text-base font-semibold text-ink">Signals AuthWho may use</legend>
      <p className="text-sm text-muted">
        Untick a channel to opt out of it. An opted-out channel is never captured, and opting out never stops
        you from using the app.
      </p>
      {CHANNELS.map((channel) => (
        <CheckboxField
          key={channel.name}
          name={`channel-${channel.name}`}
          label={channel.label}
          description={channel.description}
          checked={value[channel.name]}
          onChange={(checked) => onChange({ ...value, [channel.name]: checked })}
        />
      ))}
    </fieldset>
  );
}
