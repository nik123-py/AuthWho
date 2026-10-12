"""Per-user profile templates and runtime channel scoring (docs/interfaces.md section 9).

A template is a JSON document (never a pickle) holding:
- the fitted one-class model's parameters (scaled Manhattan by default, the
  most robust detector across the P1 and P2 experiments with small
  enrollments);
- the per-feature mean and mean absolute deviation of the enrollment windows,
  used to name the features that deviate most (explanations);
- a calibration set: raw model scores of enrollment windows, each scored by a
  model fitted without it (k-fold cross-validation).

Calibration turns the unbounded raw score into a match score in (0, 1): the
share of the user's own held-out enrollment scores that are at or below the
new window's score, smoothed as (count + 0.5) / (n + 1). A genuine window
therefore scores roughly uniformly in (0, 1). Below the lowest calibration
score the empirical rate cannot go lower than its floor 0.5 / (n + 1), so the
score keeps decaying from that floor as floor * exp(-(lowest - raw) / spread),
where spread is the larger of the robust spread (1.4826 times the median
absolute deviation) of the calibration scores and their median's magnitude; a window far less like the user than any enrollment
window therefore scores close to 0 even with a small enrollment. Scores never
go below ``MIN_SCORE``. It is a per-user p-value, which the trust engine can
threshold consistently across users and channels.

Confidence is the window's quality (share of features measured rather than
filled). Windows whose quality is below ``MIN_QUALITY`` are not scored.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from ml.models import MODEL_CLASSES, from_params

TEMPLATE_FORMAT = "authwho-template-1"
MIN_WINDOWS = 5
MIN_QUALITY = 0.5
FOLDS = 5
TOP_FEATURES = 3
MIN_SCORE = 1e-6


def _model_version(channel: str, model_kind: str) -> str:
    return f"{channel}-{model_kind}-1"


def train_template(
    channel: str,
    schema: str,
    names: Sequence[str],
    X,
    quality: Sequence[float],
    model_kind: str = "scaled_manhattan",
    seed: int = 0,
) -> dict[str, Any]:
    X = np.asarray(X, dtype=float)
    if X.ndim != 2 or X.shape[1] != len(names):
        raise ValueError("enrollment matrix does not match the feature names")
    if X.shape[0] < MIN_WINDOWS:
        raise ValueError(f"need at least {MIN_WINDOWS} enrollment windows")
    if not np.all(np.isfinite(X)):
        raise ValueError("enrollment features must be finite")
    cls = MODEL_CLASSES[model_kind]
    make = (lambda: cls(seed=seed)) if "seed" in cls.__init__.__code__.co_varnames else cls

    rng = np.random.default_rng(seed)
    order = rng.permutation(X.shape[0])
    folds = np.array_split(order, min(FOLDS, X.shape[0]))
    calibration = []
    for held in folds:
        keep = np.setdiff1d(order, held)
        calibration += make().fit(X[keep]).score(X[held]).tolist()

    mean = X.mean(axis=0)
    mad = np.maximum(np.abs(X - mean).mean(axis=0), 1e-6)
    return {
        "format": TEMPLATE_FORMAT,
        "channel": channel,
        "schema": schema,
        "feature_names": list(names),
        "model_version": _model_version(channel, model_kind),
        "model": make().fit(X).to_params(),
        "feature_mean": mean.tolist(),
        "feature_mad": mad.tolist(),
        "calibration": sorted(float(c) for c in calibration),
        "n_windows": int(X.shape[0]),
        "enrollment_quality_mean": float(np.mean(quality)),
    }


def score_window(template: dict[str, Any], x, quality: float) -> dict[str, Any]:
    x = np.asarray(x, dtype=float).ravel()
    names = template["feature_names"]
    if x.size != len(names):
        raise ValueError(f"expected {len(names)} features, got {x.size}")
    kind = template["model"]["model_kind"]
    base = {"model_kind": kind, "model_version": template["model_version"]}
    if quality < MIN_QUALITY:
        return {"status": "low_quality", "score": None, "confidence": None, "top_features": [], **base}

    raw = float(from_params(template["model"]).score(x[None, :])[0])
    cal = np.asarray(template["calibration"], dtype=float)
    score = (np.searchsorted(cal, raw, side="right") + 0.5) / (cal.size + 1)
    if raw < cal[0]:
        spread = max(1.4826 * float(np.median(np.abs(cal - np.median(cal)))),
                     abs(float(np.median(cal))), 1e-6)
        score *= float(np.exp(-(cal[0] - raw) / spread))
    score = max(float(score), MIN_SCORE)

    z = (x - np.asarray(template["feature_mean"])) / np.asarray(template["feature_mad"])
    top = np.argsort(-np.abs(z))[:TOP_FEATURES]
    return {
        "status": "scored",
        "score": float(score),
        "confidence": float(quality),
        "top_features": [{"name": names[i], "z": round(float(z[i]), 2)} for i in top],
        **base,
    }
