"""Isolation Forest detector with a JSON tree export.

scikit-learn's ``IsolationForest`` is fitted with a fixed seed, then each
tree is exported as plain arrays (children, split feature mapped back to the
original column, threshold, samples per node). Scoring reproduces
scikit-learn's ``score_samples``:

    h(x)  = depth of the leaf reached + c(n_leaf)
    score = -2 ** (-mean over trees of h(x) / c(max_samples))

where c(n) is the average path length of an unsuccessful binary search tree
lookup: 0 for n <= 1, 1 for n = 2, otherwise
2 (ln(n - 1) + Euler's gamma) - 2 (n - 1) / n.
Higher means more genuine. As in scikit-learn, inputs are cast to float32
before comparison with the split thresholds.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest

from ml.models.base import OneClassModel

EULER_GAMMA = float(np.euler_gamma)


def average_path_length(n) -> np.ndarray:
    n = np.atleast_1d(np.asarray(n, dtype=float))
    out = np.zeros_like(n)
    out[n == 2] = 1.0
    big = n > 2
    out[big] = 2.0 * (np.log(n[big] - 1.0) + EULER_GAMMA) - 2.0 * (n[big] - 1.0) / n[big]
    return out


class IsolationForestModel(OneClassModel):
    kind = "isolation_forest"

    def __init__(self, n_estimators: int = 100, seed: int = 0) -> None:
        super().__init__()
        self.n_estimators = n_estimators
        self.seed = seed
        self.max_samples: int | None = None
        self.trees: list[dict] | None = None

    def _fit(self, X):
        forest = IsolationForest(n_estimators=self.n_estimators, random_state=self.seed).fit(X)
        self.max_samples = int(forest.max_samples_)
        self.trees = []
        for est, feats in zip(forest.estimators_, forest.estimators_features_):
            t = est.tree_
            left = t.children_left.astype(int)
            mapped = np.asarray(feats)[np.maximum(t.feature, 0)]
            feature = np.where(left == -1, -1, mapped)
            self.trees.append(
                {
                    "left": left.tolist(),
                    "right": t.children_right.astype(int).tolist(),
                    "feature": feature.astype(int).tolist(),
                    "threshold": t.threshold.astype(float).tolist(),
                    "n_samples": t.n_node_samples.astype(int).tolist(),
                }
            )

    def _score(self, X):
        Xf = X.astype(np.float32).astype(np.float64)
        rows = np.arange(Xf.shape[0])
        total = np.zeros(Xf.shape[0])
        for tree in self.trees:
            left = np.asarray(tree["left"])
            right = np.asarray(tree["right"])
            feature = np.asarray(tree["feature"])
            threshold = np.asarray(tree["threshold"], dtype=float)
            n_samples = np.asarray(tree["n_samples"])
            node = np.zeros(Xf.shape[0], dtype=int)
            depth = np.zeros(Xf.shape[0])
            active = left[node] != -1
            while active.any():
                a = rows[active]
                cur = node[a]
                go_left = Xf[a, feature[cur]] <= threshold[cur]
                node[a] = np.where(go_left, left[cur], right[cur])
                depth[a] += 1.0
                active = left[node] != -1
            total += depth + average_path_length(n_samples[node])
        denom = len(self.trees) * average_path_length(self.max_samples)[0]
        return -(2.0 ** (-total / denom))

    def _params(self):
        return {
            "n_estimators": self.n_estimators,
            "seed": self.seed,
            "max_samples": self.max_samples,
            "trees": self.trees,
        }

    def _load(self, params):
        self.n_estimators = int(params["n_estimators"])
        self.seed = int(params["seed"])
        self.max_samples = int(params["max_samples"])
        self.trees = params["trees"]
