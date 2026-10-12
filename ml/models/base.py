"""Shared interface for one-class detectors.

Every detector is trained on genuine samples only and exposes:

- ``fit(X_genuine)`` returning the fitted model;
- ``score(X)`` returning one float per row, higher meaning more genuine;
- ``to_params()`` returning a JSON-serialisable dict that fully describes
  the fitted model (never a pickle);
- ``from_params(params)`` rebuilding a model whose scores are identical.

Scoring is always computed in numpy from the stored parameters, so a model
restored from JSON produces bit-identical scores to the original.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

PARAMS_FORMAT = 1


class OneClassModel:
    kind: ClassVar[str] = ""

    def __init__(self) -> None:
        self.n_features: int | None = None

    # Subclasses implement these four.
    def _fit(self, X: np.ndarray) -> None:
        raise NotImplementedError

    def _score(self, X: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def _params(self) -> dict[str, Any]:
        raise NotImplementedError

    def _load(self, params: dict[str, Any]) -> None:
        raise NotImplementedError

    def fit(self, X_genuine) -> "OneClassModel":
        X = _as_matrix(X_genuine)
        if X.shape[0] < 2:
            raise ValueError("need at least two genuine samples to fit")
        self.n_features = X.shape[1]
        self._fit(X)
        return self

    def score(self, X) -> np.ndarray:
        if self.n_features is None:
            raise RuntimeError(f"{self.kind} model is not fitted")
        X = _as_matrix(X)
        if X.shape[1] != self.n_features:
            raise ValueError(f"expected {self.n_features} features, got {X.shape[1]}")
        return np.asarray(self._score(X), dtype=float).ravel()

    def to_params(self) -> dict[str, Any]:
        if self.n_features is None:
            raise RuntimeError(f"{self.kind} model is not fitted")
        return {
            "model_kind": self.kind,
            "format": PARAMS_FORMAT,
            "n_features": int(self.n_features),
            **self._params(),
        }

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> "OneClassModel":
        if params.get("model_kind") != cls.kind:
            raise ValueError(f"params are for {params.get('model_kind')!r}, not {cls.kind!r}")
        if params.get("format") != PARAMS_FORMAT:
            raise ValueError(f"unsupported params format {params.get('format')!r}")
        model = cls()
        model.n_features = int(params["n_features"])
        model._load(params)
        return model


def _as_matrix(X) -> np.ndarray:
    arr = np.asarray(X, dtype=float)
    if arr.ndim != 2:
        raise ValueError("X must be a 2-D array (samples by features)")
    if not np.all(np.isfinite(arr)):
        raise ValueError("X must be finite")
    return arr


class Standardiser:
    """Per-feature z-scoring fitted on genuine training data, with a floor on the scale."""

    def __init__(self, mean=None, scale=None, min_scale: float = 1e-6) -> None:
        self.mean = None if mean is None else np.asarray(mean, dtype=float)
        self.scale = None if scale is None else np.asarray(scale, dtype=float)
        self.min_scale = min_scale

    def fit(self, X: np.ndarray) -> "Standardiser":
        self.mean = X.mean(axis=0)
        self.scale = np.maximum(X.std(axis=0), self.min_scale)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mean) / self.scale

    def to_params(self) -> dict[str, Any]:
        return {"mean": self.mean.tolist(), "scale": self.scale.tolist()}

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> "Standardiser":
        return cls(mean=params["mean"], scale=params["scale"])
