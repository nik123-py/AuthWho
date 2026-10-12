"""Basic bot and replay checks on window features (docs/interfaces.md section 10).

These run independently of the user's profile (proposal Section 8, step 7):

- timing_regularity: people cannot hold keys or pace keystrokes with
  machine regularity. A keystroke window whose dwell and flight standard
  deviations are both below ``REGULAR_MS`` (2 ms) is flagged with high
  severity (confirmed automation); a down-down standard deviation below
  ``SEMI_REGULAR_MS`` (5 ms) alone is flagged medium.
- implausible_motion: a pointer window whose strokes are all perfectly
  straight with constant speed (efficiency above 0.9999, mean heading change
  below 1e-4 radians, mean acceleration below 1e-6) is flagged high. A mean
  peak speed above ``MAX_SPEED`` (20 px per ms) is flagged medium only: on the
  Balabit data, recorded over remote desktop with coarse timestamps, 54 of
  4,182 genuine windows (1.3%) exceeded it, so speed alone never ends a session.
  Neither check flagged any of 7,078 Aalto keystroke windows or 776 SapiMouse
  pointer windows.
- replay_match: a window whose feature vector equals one of the user's stored
  windows from the last 30 days to a relative tolerance of 1e-6 is flagged
  high. Overlapping genuine windows share only part of their actions and never
  match this closely; recorded behaviour played back does.

A population-likeness check (population_like) is not implemented in the MVP.
Evidence strings carry numbers only, never raw events.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

REGULAR_MS = 2.0
SEMI_REGULAR_MS = 5.0
MAX_SPEED = 20.0
REPLAY_TOLERANCE = 1e-6


def _flag(kind: str, severity: str, evidence: str) -> dict:
    return {"kind": kind, "severity": severity, "evidence": evidence}


def check_window(channel: str, names: Sequence[str], values: Sequence[float]) -> list[dict]:
    v = dict(zip(names, values))
    if channel == "keystroke":
        if v["dwell_std"] < REGULAR_MS and v["flight_std"] < REGULAR_MS:
            return [_flag("timing_regularity", "high",
                          f"key hold and gap variation were {v['dwell_std']:.1f} ms and {v['flight_std']:.1f} ms")]
        if v["dd_std"] < SEMI_REGULAR_MS:
            return [_flag("timing_regularity", "medium", f"keystroke pacing varied by only {v['dd_std']:.1f} ms")]
    elif channel == "pointer":
        if v["efficiency_mean"] > 0.9999 and v["angle_change_mean"] < 1e-4 and v["acceleration_mean"] < 1e-6:
            return [_flag("implausible_motion", "high", "every pointer stroke was perfectly straight at constant speed")]
        if v["velocity_peak_mean"] > MAX_SPEED:
            return [_flag("implausible_motion", "medium",
                          f"mean peak pointer speed was {v['velocity_peak_mean'] * 1000:.0f} px per second")]
    return []


def replay_flag(values: Sequence[float], stored: Sequence[Sequence[float]]) -> dict | None:
    x = np.asarray(values, dtype=float)
    for s in stored:
        y = np.asarray(s, dtype=float)
        if y.shape == x.shape and np.all(np.abs(x - y) <= REPLAY_TOLERANCE * (np.abs(y) + 1.0)):
            return _flag("replay_match", "high", "a window matched a stored window from the last 30 days exactly")
    return None
