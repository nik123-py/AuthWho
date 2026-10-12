"""CMU keystroke dynamics benchmark (Killourhy and Maxion, 2009).

Source: https://www.cs.cmu.edu/~keystroke/ (``DSL-StrongPasswordData.csv``).
51 subjects typed the password ``.tie5Roanl`` 400 times in 8 sessions of 50
repetitions. Each row holds 31 timing features in seconds: hold times
(``H.*``), keydown-keydown latencies (``DD.*``) and keyup-keydown latencies
(``UD.*``).

The standard protocol from the paper, for each subject in turn:
- train on that subject's first 200 repetitions;
- genuine test: the subject's remaining 200 repetitions;
- impostor test: the first 5 repetitions of each of the other 50 subjects.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ID_COLUMNS = ("subject", "sessionIndex", "rep")


@dataclass(frozen=True)
class CMUData:
    subjects: list[str]
    feature_names: list[str]
    X: np.ndarray  # rows grouped by subject, each subject in typing order
    subject: np.ndarray  # subject label per row


@dataclass(frozen=True)
class ProtocolSplit:
    subject: str
    train: np.ndarray
    genuine: np.ndarray
    impostor: np.ndarray


def load_cmu(path: str | Path) -> CMUData:
    df = pd.read_csv(path)
    for col in ID_COLUMNS:
        if col not in df.columns:
            raise ValueError(f"missing column {col!r}")
    feature_names = [c for c in df.columns if c not in ID_COLUMNS]
    df = df.sort_values(["subject", "sessionIndex", "rep"], kind="stable").reset_index(drop=True)
    X = df[feature_names].to_numpy(dtype=float)
    if not np.all(np.isfinite(X)):
        raise ValueError("CMU features must be finite")
    return CMUData(
        subjects=sorted(df["subject"].unique().tolist()),
        feature_names=feature_names,
        X=X,
        subject=df["subject"].to_numpy(dtype=str),
    )


def standard_protocol(
    data: CMUData, n_train: int = 200, n_impostor_reps: int = 5
) -> Iterator[ProtocolSplit]:
    """Yield one train, genuine and impostor split per subject."""
    per_subject = {s: data.X[data.subject == s] for s in data.subjects}
    for s, rows in per_subject.items():
        if rows.shape[0] <= n_train or rows.shape[0] < n_impostor_reps:
            raise ValueError(f"subject {s} has too few repetitions for the protocol")
    for s in data.subjects:
        rows = per_subject[s]
        impostor = np.vstack(
            [per_subject[o][:n_impostor_reps] for o in data.subjects if o != s]
        )
        yield ProtocolSplit(subject=s, train=rows[:n_train], genuine=rows[n_train:], impostor=impostor)


# The password .tie5Roanl followed by Return, as the CMU column names spell it.
CMU_KEYS: tuple[str, ...] = ("period", "t", "i", "e", "five", "Shift.r", "o", "a", "n", "l", "Return")
_CMU_CATEGORY = {"period": 7, "five": 2, "Return": 7}  # every other key is a letter
_UD_TOLERANCE_S = 1e-3


def presses_from_row(values: np.ndarray, feature_names: list[str]):
    """Rebuild one repetition's eleven key presses from its timing columns.

    Key-down times follow from the down-down latencies, key-up times from the
    hold times. The key-up to key-down columns are redundant (UD = DD - H) and
    are used only as a consistency check. Times are returned in milliseconds
    from the first key-down. ``key_id`` is the key's position in the password.
    """
    from ml.datasets.presses import Press

    col = {name: float(v) for name, v in zip(feature_names, values)}
    presses = []
    down = 0.0
    for i, key in enumerate(CMU_KEYS):
        hold = col[f"H.{key}"]
        presses.append(
            Press(category=_CMU_CATEGORY.get(key, 1), key_id=i, down_t=1000.0 * down, up_t=1000.0 * (down + hold))
        )
        if i + 1 < len(CMU_KEYS):
            nxt = CMU_KEYS[i + 1]
            dd = col[f"DD.{key}.{nxt}"]
            ud = col[f"UD.{key}.{nxt}"]
            if abs((dd - hold) - ud) > _UD_TOLERANCE_S:
                raise ValueError(f"inconsistent timing columns after key {i}")
            down += dd
    return presses
