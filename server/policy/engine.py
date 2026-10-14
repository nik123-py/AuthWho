"""Policy engine: trust levels, outcomes and explanations (docs/interfaces.md section 11).

Pure functions with no I/O. The model never acts on its own: ``classify``
turns a trust update (``ml.trust``) and bot flags into one of the five trust
levels of proposal Section 7, and ``decide`` turns a level and the sensitivity
of the requested action into an outcome. Ruling R6: a strong deviation asks
for step-up first; only a failed step-up or confirmed automation is critical.

Levels:
- insufficient_signal: no fresh scored channel; normal session rules apply;
- critical: confirmed automation (a high-severity timing_regularity or
  implausible_motion flag), or a failed step-up;
- strong_deviation: trust below ``strong`` with two or more fresh channels
  scoring below ``channel_low``, or a replay_match or population_like flag of
  medium or high severity;
- moderate_deviation: trust below ``high``, or one fresh channel below
  ``channel_low``;
- high_confidence: otherwise.

``explain`` writes one plain-language sentence for administrators, naming
the behaviours that moved (never raw feature names). ``explain_for_user``
writes a neutral sentence for the session operator that reveals no scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LEVELS = ("insufficient_signal", "high_confidence", "moderate_deviation", "strong_deviation", "critical")
AUTOMATION_KINDS = {"timing_regularity", "implausible_motion"}
REPLAY_KINDS = {"replay_match", "population_like"}


@dataclass(frozen=True)
class Policy:
    policy_id: str = "default"
    version: str = "policy-1"
    high: float = 75.0
    strong: float = 50.0
    channel_low: float = 0.1
    action_sensitivity: dict[str, str] = field(default_factory=lambda: {"add_payee": "high", "export_report": "high"})


DEFAULT_POLICY = Policy()


def _low_channels(update: dict[str, Any], policy: Policy) -> list[str]:
    return [
        name for name, c in update["channels"].items()
        if c.get("fresh") and c.get("status") == "scored" and c.get("score") is not None
        and c["score"] < policy.channel_low
    ]


def classify(update: dict[str, Any] | None, policy: Policy, step_up_failed: bool = False) -> str:
    if step_up_failed:
        return "critical"
    flags = (update or {}).get("bot_flags", [])
    if any(f["kind"] in AUTOMATION_KINDS and f["severity"] == "high" for f in flags):
        return "critical"
    if any(f["kind"] in REPLAY_KINDS and f["severity"] in ("medium", "high") for f in flags):
        return "strong_deviation"
    if update is None or update.get("state") != "scored" or update.get("trust") is None:
        return "insufficient_signal"
    low = _low_channels(update, policy)
    trust = float(update["trust"])
    if trust < policy.strong and len(low) >= 2:
        return "strong_deviation"
    if trust < policy.high or len(low) == 1:
        return "moderate_deviation"
    return "high_confidence"


def decide(level: str, sensitivity: str | None) -> tuple[str, bool]:
    """Outcome and whether a pending action may proceed."""
    if level == "critical":
        return "terminate", False
    if level == "strong_deviation":
        return "step_up", False
    if level == "moderate_deviation":
        if sensitivity == "high":
            return "step_up", False
        return "monitor", True
    return "continue", True


# Plain names for the behaviours behind feature names (prefix match).
_BEHAVIOUR = [
    ("flight", "the gap between keys"),
    ("dwell", "how long keys are held"),
    ("dd_", "typing speed"),
    ("dg_", "the timing between kinds of keys"),
    ("typing_rate", "typing speed"),
    ("rollover", "overlapping key presses"),
    ("overlap", "overlapping key presses"),
    ("correction", "how mistakes are corrected"),
    ("hesitation", "pauses while typing"),
    ("pause", "pauses while typing"),
    ("velocity", "pointer speed"),
    ("acceleration", "pointer acceleration"),
    ("jerk", "pointer smoothness"),
    ("curvature", "how curved pointer paths are"),
    ("angle_change", "how pointer paths turn"),
    ("efficiency", "how direct pointer paths are"),
    ("duration", "how long pointer movements take"),
    ("path_length", "how far the pointer moves"),
    ("pre_click", "the pause before clicks"),
    ("click", "clicking"),
    ("scroll", "scrolling"),
    ("wheel", "scrolling"),
    ("focus", "moving between form fields"),
    ("field_order", "the order fields are filled in"),
    ("paste", "pasting"),
    ("gap", "the pace of page interaction"),
    ("event_rate", "the pace of page interaction"),
    ("span", "the pace of page interaction"),
]
_CHANNEL_NAME = {"keystroke": "typing rhythm", "pointer": "mouse movement", "interaction": "page interaction"}


def behaviour(feature: str) -> str:
    for prefix, text in _BEHAVIOUR:
        if feature.startswith(prefix):
            return text
    return "behaviour"


def _main_behaviours(update: dict[str, Any], channels: list[str]) -> list[str]:
    out = []
    for c in channels:
        for f in update["channels"][c].get("top_features", [])[:1]:
            b = behaviour(f["name"])
            if b not in out:
                out.append(b)
    return out


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def explain(level: str, update: dict[str, Any] | None, step_up_failed: bool = False,
            policy: Policy = DEFAULT_POLICY) -> str:
    flags = (update or {}).get("bot_flags", [])
    if level == "critical" and not step_up_failed:
        kinds = {f["kind"] for f in flags if f["severity"] == "high"}
        if "timing_regularity" in kinds:
            return "Key timing was too regular for a person, which suggests automated input, so the session was ended."
        return "Pointer movement was physically implausible for a person, which suggests automated input, so the session was ended."
    if level == "insufficient_signal":
        return "There was not enough recent typing or pointer activity to judge who is using the session."
    low = _low_channels(update, policy) if update else []
    scored = [c for c, v in (update or {}).get("channels", {}).items() if v.get("fresh")]
    if level == "critical":
        moved = _join([_CHANNEL_NAME[c] for c in low]) if low else "behaviour"
        return f"The identity check failed after {moved} diverged from this user's profile, so the session was ended."
    if level == "strong_deviation" and any(f["kind"] in REPLAY_KINDS for f in flags):
        return "Recent behaviour matched previously recorded behaviour too closely, which suggests a replay."
    if level == "high_confidence":
        names = _join([_CHANNEL_NAME[c] for c in scored]) if scored else "behaviour"
        verb = "match" if len(scored) > 1 else "matches"
        return f"{names[0].upper() + names[1:]} {verb} this user's profile within normal variation."
    channels = low or scored
    names = _join([_CHANNEL_NAME[c] for c in channels])
    detail = _main_behaviours(update, channels)
    tail = f", mainly {_join(detail)}" if detail else ""
    if level == "strong_deviation":
        together = "both" if len(channels) == 2 else "all"
        return f"{names[0].upper() + names[1:]} {together} diverged from this user's profile{tail}."
    still = [c for c in scored if c not in low]
    if low and still:
        return (f"{names[0].upper() + names[1:]} moved away from this user's profile{tail}, while "
                f"{_join([_CHANNEL_NAME[c] for c in still])} still matches.")
    return f"{names[0].upper() + names[1:]} moved away from this user's profile{tail}."


_USER_TEXT = {
    "continue": "You can continue.",
    "monitor": "You can continue.",
    "step_up": "Please confirm it is you to continue.",
    "terminate": "For your security this session has ended. Please sign in again.",
}


def explain_for_user(outcome: str) -> str:
    return _USER_TEXT[outcome]
