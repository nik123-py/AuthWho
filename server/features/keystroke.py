"""kf-1 keystroke features (docs/interfaces.md section 8).

Input: completed key presses carrying only a key category and two times in
milliseconds. No key identity exists at this level. Presses are sorted by
key-down time; "consecutive" below means neighbours in that order.

Definitions:
- dwell = up_t - down_t of one press. ``dwell_mean``, ``_std`` (population),
  ``_median``, ``_p10``, ``_p90``.
- flight = next down_t - previous up_t, clipped to [-500, 2000] ms; negative
  when keys overlap. Same five statistics.
- dd (down-down latency) = next down_t - previous down_t, clipped to
  [0, 2000] ms. Mean, std and median.
- ``rollover_rate``: share of consecutive pairs where the next key goes down
  before the previous one is released. ``overlap_mean``: mean over all
  consecutive pairs of max(0, previous up_t - next down_t).
- ``dwell_<category>``: mean dwell of presses in that category.
  Fill: ``dwell_median`` when the window has no press of that category.
- ``dg_<a>_<b>``: median clipped dd latency over consecutive pairs from
  category a to category b. Fill: ``dd_median`` when the pair does not occur.
- ``correction_rate``: share of presses in the backspace category.
  ``correction_burst_len``: mean length of runs of consecutive backspace
  presses. Fill: 0 when there are no corrections.
- Gaps are unclipped dd latencies. ``pause_rate``: share of gaps over 2000 ms.
  ``hesitation_rate``: share of gaps in (500, 2000] ms. ``typing_rate``:
  presses per second while typing, that is the number of gaps of at most
  2000 ms divided by their total duration in seconds. Fill: 0 when every gap
  is a pause.

``quality`` = 1 - (number of filled features / number of features).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from server.features.schemas import KF1, KF1_DIGRAPHS, KF1_DWELL_CATEGORIES, KF1_NAMES
from server.features.types import BACKSPACE, KEY_CATEGORIES, FeatureVector, KeyPress

FLIGHT_CLIP = (-500.0, 2000.0)
DD_CLIP = (0.0, 2000.0)
PAUSE_MS = 2000.0
HESITATION_MS = 500.0


def _stats5(x: np.ndarray) -> list[float]:
    return [
        float(x.mean()),
        float(x.std()),
        float(np.median(x)),
        float(np.percentile(x, 10)),
        float(np.percentile(x, 90)),
    ]


def extract_keystroke(presses: Sequence[KeyPress]) -> FeatureVector:
    if len(presses) < 2:
        raise ValueError("a keystroke window needs at least two presses")
    for p in presses:
        if p.category not in KEY_CATEGORIES:
            raise ValueError("unknown key category")
        if not (np.isfinite(p.down_t) and np.isfinite(p.up_t)) or p.up_t < p.down_t:
            raise ValueError("key-up must be finite and not before key-down")

    ordered = sorted(presses, key=lambda p: (p.down_t, p.up_t))
    cats = [KEY_CATEGORIES[p.category] for p in ordered]
    down = np.array([p.down_t for p in ordered], dtype=float)
    up = np.array([p.up_t for p in ordered], dtype=float)

    dwell = up - down
    gaps = np.diff(down)
    flight = np.clip(down[1:] - up[:-1], *FLIGHT_CLIP)
    dd = np.clip(gaps, *DD_CLIP)
    overlap = np.maximum(0.0, up[:-1] - down[1:])

    feats: dict[str, float] = {}
    filled = 0
    for prefix, values in (("dwell", dwell), ("flight", flight)):
        for suffix, v in zip(("mean", "std", "median", "p10", "p90"), _stats5(values)):
            feats[f"{prefix}_{suffix}"] = v
    feats["dd_mean"] = float(dd.mean())
    feats["dd_std"] = float(dd.std())
    feats["dd_median"] = float(np.median(dd))
    feats["rollover_rate"] = float(np.mean(down[1:] < up[:-1]))
    feats["overlap_mean"] = float(overlap.mean())

    cat_arr = np.array(cats)
    for c in KF1_DWELL_CATEGORIES:
        mask = cat_arr == c
        if mask.any():
            feats[f"dwell_{c}"] = float(dwell[mask].mean())
        else:
            feats[f"dwell_{c}"] = feats["dwell_median"]
            filled += 1

    pairs = list(zip(cats[:-1], cats[1:]))
    for a, b in KF1_DIGRAPHS:
        vals = [dd[k] for k, pair in enumerate(pairs) if pair == (a, b)]
        if vals:
            feats[f"dg_{a}_{b}"] = float(np.median(vals))
        else:
            feats[f"dg_{a}_{b}"] = feats["dd_median"]
            filled += 1

    is_bs = np.array([p.category == BACKSPACE for p in ordered])
    feats["correction_rate"] = float(is_bs.mean())
    runs, run = [], 0
    for flag in is_bs:
        if flag:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    if run:
        runs.append(run)
    if runs:
        feats["correction_burst_len"] = float(np.mean(runs))
    else:
        feats["correction_burst_len"] = 0.0
        filled += 1

    typing_gaps = gaps[gaps <= PAUSE_MS]
    if typing_gaps.size and typing_gaps.sum() > 0:
        feats["typing_rate"] = float(typing_gaps.size / (typing_gaps.sum() / 1000.0))
    else:
        feats["typing_rate"] = 0.0
        filled += 1
    feats["hesitation_rate"] = float(np.mean((gaps > HESITATION_MS) & (gaps <= PAUSE_MS)))
    feats["pause_rate"] = float(np.mean(gaps > PAUSE_MS))

    values = [feats[n] for n in KF1_NAMES]
    if not all(np.isfinite(values)):
        raise ValueError("non-finite keystroke feature")
    return FeatureVector(
        schema=KF1,
        channel="keystroke",
        names=list(KF1_NAMES),
        values=values,
        n_actions=len(ordered),
        quality=1.0 - filled / len(KF1_NAMES),
    )
