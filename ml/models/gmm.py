"""Gaussian Mixture Model detector.

Features are z-scored with statistics of the genuine training data, then a
full-covariance ``GaussianMixture`` is fitted with a fixed seed. The stored
parameters are the standardiser and the mixture weights, means and
covariance matrices. The score is the log-likelihood of the standardised
sample under the mixture, recomputed in numpy (higher means more genuine).
"""

from __future__ import annotations

import numpy as np
from scipy.special import logsumexp
from sklearn.mixture import GaussianMixture

from ml.models.base import OneClassModel, Standardiser


class GaussianMixtureModel(OneClassModel):
    kind = "gmm"

    def __init__(self, n_components: int = 2, reg_covar: float = 1e-2, seed: int = 0) -> None:
        super().__init__()
        self.n_components = n_components
        self.reg_covar = reg_covar
        self.seed = seed
        self.std: Standardiser | None = None
        self.weights: np.ndarray | None = None
        self.means: np.ndarray | None = None
        self.covariances: np.ndarray | None = None

    def _standardise(self, X):
        return self.std.transform(np.asarray(X, dtype=float))

    def _fit(self, X):
        self.std = Standardiser().fit(X)
        gm = GaussianMixture(
            n_components=self.n_components,
            covariance_type="full",
            reg_covar=self.reg_covar,
            random_state=self.seed,
        ).fit(self._standardise(X))
        self.weights = np.asarray(gm.weights_, dtype=float)
        self.means = np.asarray(gm.means_, dtype=float)
        self.covariances = np.asarray(gm.covariances_, dtype=float)

    def _score(self, X):
        Z = self._standardise(X)
        d = Z.shape[1]
        comp = np.empty((Z.shape[0], self.weights.size))
        for k in range(self.weights.size):
            L = np.linalg.cholesky(self.covariances[k])
            sol = np.linalg.solve(L, (Z - self.means[k]).T)
            maha = (sol**2).sum(axis=0)
            log_det = 2.0 * np.log(np.diag(L)).sum()
            comp[:, k] = np.log(self.weights[k]) - 0.5 * (d * np.log(2 * np.pi) + log_det + maha)
        return logsumexp(comp, axis=1)

    def _params(self):
        return {
            "n_components": self.n_components,
            "reg_covar": self.reg_covar,
            "seed": self.seed,
            "standardiser": self.std.to_params(),
            "weights": self.weights.tolist(),
            "means": self.means.tolist(),
            "covariances": self.covariances.tolist(),
        }

    def _load(self, params):
        self.n_components = int(params["n_components"])
        self.reg_covar = float(params["reg_covar"])
        self.seed = int(params["seed"])
        self.std = Standardiser.from_params(params["standardiser"])
        self.weights = np.asarray(params["weights"], dtype=float)
        self.means = np.asarray(params["means"], dtype=float)
        self.covariances = np.asarray(params["covariances"], dtype=float)
