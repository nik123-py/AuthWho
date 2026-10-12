"""Interaction events and ``if-1`` features (docs/interfaces.md section 8).

Interaction events are event codes 6 to 13 (wheel, scroll, field focus and
blur, visibility, clipboard, page, action mark). Windows hold 20 events every
10 events.

``if-1`` features (times in ms unless named ``_s``):
- span_s: seconds from the first to the last event; event_rate: events per
  second (0 when the span is 0);
- wheel_frac, scroll_frac, focus_frac, clipboard_frac, visibility_frac,
  page_frac, action_frac: share of the window's events of each type (focus
  counts FIELD_FOCUS only);
- wheel_dy_abs_mean: mean absolute vertical wheel delta;
- scroll_direction_changes: share of consecutive vertical movements that
  reverse direction, from wheel deltas and scroll-position changes in time
  order;
- field_order_inversions: share of consecutive field focuses that move to an
  earlier field;
- focus_dwell_mean: mean time from a field focus to the next blur of the same
  field;
- hesitation_mean: mean time from the previous event to each action mark;
- paste_rate: pastes per second; gap_mean, gap_std: time between consecutive
  events, clipped to [0, 30000].
Fill rule: wheel_dy_abs_mean, scroll_direction_changes,
field_order_inversions, focus_dwell_mean and hesitation_mean are 0 when the
window has no data for them, and each such fill lowers quality.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from server.features.schemas import IF1, IF1_NAMES
from server.features.types import FeatureVector, InteractionEvent

WHEEL, SCROLL, FOCUS, BLUR, VISIBILITY, CLIPBOARD, PAGE, ACTION = 6, 7, 8, 9, 10, 11, 12, 13
PASTE = 3
GAP_CLIP = (0.0, 30000.0)
_FRACTIONS = {
    "wheel_frac": WHEEL,
    "scroll_frac": SCROLL,
    "focus_frac": FOCUS,
    "clipboard_frac": CLIPBOARD,
    "visibility_frac": VISIBILITY,
    "page_frac": PAGE,
    "action_frac": ACTION,
}


def extract_interaction(events: Sequence[InteractionEvent]) -> FeatureVector:
    if len(events) < 2:
        raise ValueError("an interaction window needs at least two events")
    ev = sorted(events, key=lambda e: e.t)
    t = np.array([e.t for e in ev], dtype=float)
    codes = [e.code for e in ev]
    n = len(ev)
    span_s = float(t[-1] - t[0]) / 1000.0
    f: dict[str, float] = {"span_s": span_s, "event_rate": n / span_s if span_s > 0 else 0.0}
    for name, code in _FRACTIONS.items():
        f[name] = codes.count(code) / n
    filled = 0

    wheel_dy = [e.values[1] for e in ev if e.code == WHEEL and len(e.values) >= 2]
    if wheel_dy:
        f["wheel_dy_abs_mean"] = float(np.mean(np.abs(wheel_dy)))
    else:
        f["wheel_dy_abs_mean"] = 0.0
        filled += 1

    moves, last_scroll_y = [], None
    for e in ev:
        if e.code == WHEEL and len(e.values) >= 2 and e.values[1] != 0:
            moves.append(np.sign(e.values[1]))
        elif e.code == SCROLL and len(e.values) >= 2:
            if last_scroll_y is not None and e.values[1] != last_scroll_y:
                moves.append(np.sign(e.values[1] - last_scroll_y))
            last_scroll_y = e.values[1]
    if len(moves) >= 2:
        f["scroll_direction_changes"] = float(np.mean([a != b for a, b in zip(moves, moves[1:])]))
    else:
        f["scroll_direction_changes"] = 0.0
        filled += 1

    focus_idx = [e.values[0] for e in ev if e.code == FOCUS and e.values]
    if len(focus_idx) >= 2:
        f["field_order_inversions"] = float(np.mean([b < a for a, b in zip(focus_idx, focus_idx[1:])]))
    else:
        f["field_order_inversions"] = 0.0
        filled += 1

    dwells, open_focus = [], {}
    for e in ev:
        if e.code == FOCUS and e.values:
            open_focus[e.values[0]] = e.t
        elif e.code == BLUR and e.values and e.values[0] in open_focus:
            dwells.append(e.t - open_focus.pop(e.values[0]))
    if dwells:
        f["focus_dwell_mean"] = float(np.mean(dwells))
    else:
        f["focus_dwell_mean"] = 0.0
        filled += 1

    hes = [ev[i].t - ev[i - 1].t for i in range(1, n) if ev[i].code == ACTION]
    if hes:
        f["hesitation_mean"] = float(np.mean(hes))
    else:
        f["hesitation_mean"] = 0.0
        filled += 1

    pastes = sum(1 for e in ev if e.code == CLIPBOARD and e.values and int(e.values[0]) == PASTE)
    f["paste_rate"] = pastes / span_s if span_s > 0 else 0.0
    gaps = np.clip(np.diff(t), *GAP_CLIP)
    f["gap_mean"] = float(gaps.mean())
    f["gap_std"] = float(gaps.std())

    values = [f[name] for name in IF1_NAMES]
    if not all(np.isfinite(values)):
        raise ValueError("non-finite interaction feature")
    return FeatureVector(
        schema=IF1,
        channel="interaction",
        names=list(IF1_NAMES),
        values=values,
        n_actions=n,
        quality=1.0 - filled / len(IF1_NAMES),
    )


class InteractionWindower:
    """Windows of ``size`` interaction events every ``stride`` events."""

    def __init__(self, size: int = 20, stride: int = 10) -> None:
        if not 0 < stride <= size:
            raise ValueError("need 0 < stride <= size")
        self.size = size
        self.stride = stride
        self._buf: list[InteractionEvent] = []

    def add(self, events: Sequence[Sequence[float]]) -> list[list[InteractionEvent]]:
        for raw in events:
            code = int(raw[0])
            if WHEEL <= code <= ACTION:
                self._buf.append(InteractionEvent(code=code, t=float(raw[1]), values=tuple(float(v) for v in raw[2:])))
        windows = []
        while len(self._buf) >= self.size:
            windows.append(self._buf[: self.size])
            del self._buf[: self.stride]
        return windows
