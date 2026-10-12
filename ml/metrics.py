"""Verification metrics for one-class detectors.

Convention used throughout: a higher score means "more genuine", and a sample
is accepted when its score is greater than or equal to the decision threshold.

- FAR (false acceptance rate): share of impostor samples accepted.
- FRR (false rejection rate): share of genuine samples rejected.
- EER (equal error rate): the error rate where FAR equals FRR. See ``eer`` for
  the interpolation method.
- ROC-AUC: probability that a random genuine sample scores above a random
  impostor sample, ties counting one half (scikit-learn implementation).
- ``bootstrap_ci``: percentile bootstrap interval over users.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from sklearn.metrics import roc_auc_score


def _as_scores(values: Sequence[float] | np.ndarray, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError(f"{name} scores must not be empty")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} scores must be finite")
    return arr


def far_frr(genuine, impostor, threshold: float) -> tuple[float, float]:
    """Return (FAR, FRR) at ``threshold``; scores >= threshold are accepted."""
    g = _as_scores(genuine, "genuine")
    i = _as_scores(impostor, "impostor")
    far = float(np.mean(i >= threshold))
    frr = float(np.mean(g < threshold))
    return far, frr


def eer(genuine, impostor) -> float:
    """Equal error rate with linear interpolation at the FAR/FRR crossing.

    Method: every distinct score, plus +infinity, is used as a threshold,
    taken in ascending order. FAR is non-increasing and FRR non-decreasing
    along this sequence, so d = FAR - FRR is non-increasing, starting at
    FAR = 1, FRR = 0 (d = 1) and ending at FAR = 0, FRR = 1 (d = -1). At the
    first operating point k with d_k <= 0, the EER is FAR_k if d_k = 0;
    otherwise the segment between operating points k-1 and k of the ROC is
    interpolated linearly to the point where FAR = FRR:
        lam = d_{k-1} / (d_{k-1} - d_k)
        EER = FAR_{k-1} + lam * (FAR_k - FAR_{k-1})
    which also equals FRR_{k-1} + lam * (FRR_k - FRR_{k-1}).
    """
    g = _as_scores(genuine, "genuine")
    i = _as_scores(impostor, "impostor")
    thresholds = np.append(np.unique(np.concatenate([g, i])), np.inf)
    g_sorted = np.sort(g)
    i_sorted = np.sort(i)
    # Number of samples strictly below each threshold.
    frr = np.searchsorted(g_sorted, thresholds, side="left") / g.size
    far = 1.0 - np.searchsorted(i_sorted, thresholds, side="left") / i.size
    d = far - frr
    k = int(np.argmax(d <= 0))  # d[-1] = -1, so a crossing always exists
    if d[k] == 0 or k == 0:
        return float(far[k])
    lam = d[k - 1] / (d[k - 1] - d[k])
    return float(far[k - 1] + lam * (far[k] - far[k - 1]))


def roc_auc(genuine, impostor) -> float:
    """ROC-AUC with genuine as the positive class (higher score = genuine)."""
    g = _as_scores(genuine, "genuine")
    i = _as_scores(impostor, "impostor")
    y = np.concatenate([np.ones(g.size), np.zeros(i.size)])
    return float(roc_auc_score(y, np.concatenate([g, i])))


def bootstrap_ci(
    values,
    statistic: Callable[[np.ndarray], float] = np.mean,
    n_resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval over users.

    ``values`` holds one number per user (for example a per-user EER). Users
    are resampled with replacement ``n_resamples`` times using
    ``numpy.random.default_rng(seed)``; ``statistic`` is computed on each
    resample, and the interval is the (1 - confidence)/2 and
    (1 + confidence)/2 percentiles of those statistics (numpy's default
    linear interpolation between order statistics).
    """
    arr = np.asarray(values, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError("values must not be empty")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    if n_resamples < 1:
        raise ValueError("n_resamples must be positive")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(n_resamples, arr.size))
    stats = np.array([statistic(arr[row]) for row in idx], dtype=float)
    alpha = (1.0 - confidence) / 2.0
    low, high = np.percentile(stats, [100 * alpha, 100 * (1 - alpha)])
    return float(low), float(high)
