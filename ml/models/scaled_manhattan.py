"""Scaled Manhattan detector (Killourhy and Maxion, 2009).

Training stores the per-feature mean and mean absolute deviation (MAD) of
the genuine samples. The anomaly score of x is sum_j |x_j - mean_j| / mad_j;
``score`` returns its negation so that higher means more genuine. A MAD
below ``min_scale`` is raised to ``min_scale`` to avoid division by zero.
"""

from __future__ import annotations

import numpy as np

from ml.models.base import OneClassModel


class ScaledManhattan(OneClassModel):
    kind = "scaled_manhattan"

    def __init__(self, min_scale: float = 1e-6) -> None:
        super().__init__()
        self.min_scale = min_scale
        self.mean: np.ndarray | None = None
        self.mad: np.ndarray | None = None

    def _fit(self, X):
        self.mean = X.mean(axis=0)
        self.mad = np.maximum(np.abs(X - self.mean).mean(axis=0), self.min_scale)

    def _score(self, X):
        return -(np.abs(X - self.mean) / self.mad).sum(axis=1)

    def _params(self):
        return {"min_scale": self.min_scale, "mean": self.mean.tolist(), "mad": self.mad.tolist()}

    def _load(self, params):
        self.min_scale = float(params["min_scale"])
        self.mean = np.asarray(params["mean"], dtype=float)
        self.mad = np.asarray(params["mad"], dtype=float)
