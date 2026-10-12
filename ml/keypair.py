"""Category-level versus key-pair keystroke features for the P1-3 experiment.

Offline research only. The live system computes ``kf-1`` from key categories
and never sees which key was pressed (proposal Section 9). This module builds
a key-pair variant from public datasets that record key identities, to measure
what the category-only choice costs.

Both variants share the 20 ``kf-1`` features that do not depend on key
identity (dwell, flight and down-down statistics, rollover, corrections,
rates). They differ only in the identity-dependent part:

- category variant: ``kf-1`` itself, with dwell per key category and
  down-down latency per category pair;
- key-pair variant: dwell for the ten most frequent keys of English text and
  down-down latency for the twenty most frequent English letter bigrams.

The key and bigram lists are fixed in advance from general English letter
statistics, not learned from the evaluation data. A key or bigram missing from
a window is filled with the window's mean dwell or mean down-down latency.
Key identities are JavaScript key codes (letters are the upper-case codes).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ml.datasets.presses import Press
from server.features.keystroke import extract_keystroke
from server.features.schemas import KF1_NAMES

SHARED_NAMES: list[str] = [n for n in KF1_NAMES if not n.startswith("dg_") and n not in {
    "dwell_letter", "dwell_digit", "dwell_space", "dwell_backspace", "dwell_modifier",
}]

# E T A O I N S H R and space.
KP1_KEYS: list[int] = [69, 84, 65, 79, 73, 78, 83, 72, 82, 32]
KP1_BIGRAMS: list[str] = [
    "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
    "ti", "es", "or", "te", "of", "ed", "is", "it", "al", "ar",
]
KP1_NAMES: list[str] = SHARED_NAMES + [f"kdwell_{k}" for k in KP1_KEYS] + [f"kdd_{b}" for b in KP1_BIGRAMS]

_BIGRAM_CODES = {(ord(b[0].upper()), ord(b[1].upper())): b for b in KP1_BIGRAMS}


def extract_category(presses: Sequence[Press]) -> tuple[list[str], list[float]]:
    """The live ``kf-1`` vector, computed from categories only."""
    fv = extract_keystroke([p.as_keypress() for p in presses])
    return fv.names, fv.values


def extract_keypair(presses: Sequence[Press]) -> np.ndarray:
    fv = extract_keystroke([p.as_keypress() for p in presses])
    base = dict(zip(fv.names, fv.values))
    ordered = sorted(presses, key=lambda p: (p.down_t, p.up_t))

    dwell: dict[int, list[float]] = {}
    for p in ordered:
        dwell.setdefault(p.key_id, []).append(p.up_t - p.down_t)
    dd: dict[str, list[float]] = {}
    for a, b in zip(ordered, ordered[1:]):
        name = _BIGRAM_CODES.get((a.key_id, b.key_id))
        if name is not None:
            dd.setdefault(name, []).append(b.down_t - a.down_t)

    values = [base[n] for n in SHARED_NAMES]
    values += [float(np.mean(dwell[k])) if k in dwell else base["dwell_mean"] for k in KP1_KEYS]
    values += [float(np.mean(dd[b])) if b in dd else base["dd_mean"] for b in KP1_BIGRAMS]
    return np.asarray(values, dtype=float)
