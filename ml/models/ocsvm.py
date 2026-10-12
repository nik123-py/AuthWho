"""One-Class SVM with an RBF kernel.

Features are z-scored with statistics of the genuine training data, then
scikit-learn's ``OneClassSVM`` is fitted. The stored parameters are the
standardiser, the support vectors, the dual coefficients, the intercept and
the resolved gamma. The decision function is recomputed in numpy:

    f(z) = sum_k alpha_k * exp(-gamma * ||z - sv_k||^2) + intercept

Higher f means more genuine (inside the learned support).
"""

from __future__ import annotations

import numpy as np
from sklearn.svm import OneClassSVM

from ml.models.base import OneClassModel, Standardiser


class OneClassSVMModel(OneClassModel):
    kind = "ocsvm"

    def __init__(self, nu: float = 0.05, gamma: str | float = "scale") -> None:
        super().__init__()
        self.nu = nu
        self.gamma_setting = gamma
        self.std: Standardiser | None = None
        self.support_vectors: np.ndarray | None = None
        self.dual_coef: np.ndarray | None = None
        self.intercept: float | None = None
        self.gamma: float | None = None

    def _standardise(self, X):
        return self.std.transform(np.asarray(X, dtype=float))

    def _fit(self, X):
        self.std = Standardiser().fit(X)
        svm = OneClassSVM(kernel="rbf", nu=self.nu, gamma=self.gamma_setting)
        svm.fit(self._standardise(X))
        self.support_vectors = np.asarray(svm.support_vectors_, dtype=float)
        self.dual_coef = np.asarray(svm.dual_coef_, dtype=float).ravel()
        self.intercept = float(np.asarray(svm.intercept_).ravel()[0])
        self.gamma = float(svm._gamma)

    def _score(self, X):
        Z = self._standardise(X)
        sq = ((Z[:, None, :] - self.support_vectors[None, :, :]) ** 2).sum(axis=2)
        return np.exp(-self.gamma * sq) @ self.dual_coef + self.intercept

    def _params(self):
        return {
            "nu": self.nu,
            "standardiser": self.std.to_params(),
            "support_vectors": self.support_vectors.tolist(),
            "dual_coef": self.dual_coef.tolist(),
            "intercept": self.intercept,
            "gamma": self.gamma,
        }

    def _load(self, params):
        self.nu = float(params["nu"])
        self.std = Standardiser.from_params(params["standardiser"])
        self.support_vectors = np.asarray(params["support_vectors"], dtype=float)
        self.dual_coef = np.asarray(params["dual_coef"], dtype=float)
        self.intercept = float(params["intercept"])
        self.gamma = float(params["gamma"])
