"""Ordered feature names per schema version (docs/interfaces.md section 8).

Changing a name or the order requires a new schema version. The meaning and
fill rule of every kf-1 feature is documented in ``server/features/keystroke.py``.
"""

from __future__ import annotations

KF1 = "kf-1"
KF1_EXTRACTOR_VERSION = "kf-1.0"

KF1_DIGRAPHS: list[tuple[str, str]] = [
    ("letter", "letter"),
    ("letter", "space"),
    ("space", "letter"),
    ("letter", "backspace"),
    ("backspace", "backspace"),
    ("backspace", "letter"),
    ("letter", "other"),
    ("other", "space"),
    ("modifier", "letter"),
    ("digit", "digit"),
]

KF1_DWELL_CATEGORIES: list[str] = ["letter", "digit", "space", "backspace", "modifier"]

KF1_NAMES: list[str] = [
    "dwell_mean", "dwell_std", "dwell_median", "dwell_p10", "dwell_p90",
    "flight_mean", "flight_std", "flight_median", "flight_p10", "flight_p90",
    "dd_mean", "dd_std", "dd_median",
    "rollover_rate", "overlap_mean",
    *[f"dwell_{c}" for c in KF1_DWELL_CATEGORIES],
    *[f"dg_{a}_{b}" for a, b in KF1_DIGRAPHS],
    "correction_rate", "correction_burst_len",
    "typing_rate", "hesitation_rate", "pause_rate",
]

PF1 = "pf-1"
PF1_EXTRACTOR_VERSION = "pf-1.0"

# Per-stroke measures aggregated over a window as mean and standard deviation.
# Their definitions are in ``server/features/pointer.py``.
PF1_STROKE_MEASURES: list[str] = [
    "duration", "path_length", "efficiency", "velocity", "velocity_peak",
    "acceleration", "jerk", "curvature", "angle_change",
]

PF1_NAMES: list[str] = [
    *[f"{m}_{s}" for m in PF1_STROKE_MEASURES for s in ("mean", "std")],
    "pauses_mean", "click_rate", "pre_click_pause_mean", "click_hold_mean",
]

IF1 = "if-1"
IF1_EXTRACTOR_VERSION = "if-1.0"

# Definitions and fill rules are in ``server/features/interaction.py``.
IF1_NAMES: list[str] = [
    "span_s", "event_rate",
    "wheel_frac", "scroll_frac", "focus_frac", "clipboard_frac", "visibility_frac", "page_frac", "action_frac",
    "wheel_dy_abs_mean", "scroll_direction_changes", "field_order_inversions", "focus_dwell_mean",
    "hesitation_mean", "paste_rate", "gap_mean", "gap_std",
]
