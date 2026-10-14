/** Plain-language names for levels, statuses, channels and features (mirrors server/policy/engine.py). */

export const LEVEL_LABEL: Record<string, string> = {
  insufficient_signal: "Cannot determine",
  high_confidence: "High confidence",
  moderate_deviation: "Moderate deviation",
  strong_deviation: "Strong deviation",
  critical: "Critical",
};

export const STATUS_LABEL: Record<string, string> = {
  active: "Active",
  step_up_required: "Step-up required",
  terminated: "Ended",
};

export const CHANNEL_LABEL: Record<string, string> = {
  keystroke: "Typing rhythm",
  pointer: "Mouse movement",
  interaction: "Page interaction",
};

export const CHANNEL_STATUS_LABEL: Record<string, string> = {
  no_profile: "Enrolling",
  opted_out: "Opted out",
  low_quality: "Too little data",
};

export const OUTCOME_LABEL: Record<string, string> = {
  continue: "Continue",
  monitor: "Monitor",
  step_up: "Step-up",
  terminate: "End session",
};

const BEHAVIOUR: [string, string][] = [
  ["flight", "the gap between keys"],
  ["dwell", "how long keys are held"],
  ["dd_", "typing speed"],
  ["dg_", "the timing between kinds of keys"],
  ["typing_rate", "typing speed"],
  ["rollover", "overlapping key presses"],
  ["overlap", "overlapping key presses"],
  ["correction", "how mistakes are corrected"],
  ["hesitation", "pauses while typing"],
  ["pause", "pauses while typing"],
  ["velocity", "pointer speed"],
  ["acceleration", "pointer acceleration"],
  ["jerk", "pointer smoothness"],
  ["curvature", "how curved pointer paths are"],
  ["angle_change", "how pointer paths turn"],
  ["efficiency", "how direct pointer paths are"],
  ["duration", "how long pointer movements take"],
  ["path_length", "how far the pointer moves"],
  ["pre_click", "the pause before clicks"],
  ["click", "clicking"],
  ["scroll", "scrolling"],
  ["wheel", "scrolling"],
  ["focus", "moving between form fields"],
  ["field_order", "the order fields are filled in"],
  ["paste", "pasting"],
  ["gap", "the pace of page interaction"],
  ["event_rate", "the pace of page interaction"],
  ["span", "the pace of page interaction"],
];

export function behaviour(feature: string): string {
  return BEHAVIOUR.find(([prefix]) => feature.startsWith(prefix))?.[1] ?? "behaviour";
}

export function formatTrust(trust: number | null | undefined): string {
  return trust === null || trust === undefined ? "Cannot determine" : trust.toFixed(1);
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString();
}
