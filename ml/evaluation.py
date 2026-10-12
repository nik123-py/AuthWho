"""Per-user evaluation of one-class detectors.

Each split holds one user's training rows, held-out genuine rows and impostor
rows. A fresh detector is fitted per user; the user's EER and ROC-AUC are
computed from its scores. Summaries average over users (each user counts
once, as in Killourhy and Maxion) and add a bootstrap interval over users.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import numpy as np

from ml.metrics import bootstrap_ci, eer, roc_auc
from ml.models.base import OneClassModel


def evaluate_splits(splits: Iterable, factory: Callable[[], OneClassModel]) -> list[dict[str, Any]]:
    rows = []
    for split in splits:
        model = factory().fit(split.train)
        g = model.score(split.genuine)
        i = model.score(split.impostor)
        rows.append(
            {
                "subject": split.subject,
                "n_train": int(split.train.shape[0]),
                "n_genuine": int(g.size),
                "n_impostor": int(i.size),
                "eer": eer(g, i),
                "roc_auc": roc_auc(g, i),
            }
        )
    return rows


def summarise(rows: list[dict[str, Any]], seed: int = 0) -> dict[str, Any]:
    out: dict[str, Any] = {"n_users": len(rows)}
    for key in ("eer", "roc_auc"):
        vals = np.array([r[key] for r in rows], dtype=float)
        out[f"{key}_mean"] = float(vals.mean())
        out[f"{key}_sd"] = float(vals.std(ddof=1)) if vals.size > 1 else 0.0
        out[f"{key}_ci95"] = list(bootstrap_ci(vals, seed=seed))
    return out
