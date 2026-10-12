"""One-class detectors sharing the interface in ``ml.models.base``."""

from __future__ import annotations

from typing import Any

from ml.models.base import OneClassModel
from ml.models.gmm import GaussianMixtureModel
from ml.models.iforest import IsolationForestModel
from ml.models.ocsvm import OneClassSVMModel
from ml.models.scaled_manhattan import ScaledManhattan

MODEL_CLASSES: dict[str, type[OneClassModel]] = {
    cls.kind: cls
    for cls in (ScaledManhattan, OneClassSVMModel, GaussianMixtureModel, IsolationForestModel)
}


def from_params(params: dict[str, Any]) -> OneClassModel:
    """Rebuild a fitted model from the dict produced by ``to_params``."""
    kind = params.get("model_kind")
    if kind not in MODEL_CLASSES:
        raise ValueError(f"unknown model_kind {kind!r}")
    return MODEL_CLASSES[kind].from_params(params)


__all__ = [
    "MODEL_CLASSES",
    "GaussianMixtureModel",
    "IsolationForestModel",
    "OneClassModel",
    "OneClassSVMModel",
    "ScaledManhattan",
    "from_params",
]
