"""Per-user evaluation over train, genuine and impostor splits."""

import numpy as np
import pytest

from ml.datasets.cmu import ProtocolSplit
from ml.evaluation import evaluate_splits, summarise
from ml.models import ScaledManhattan


def _splits(separation):
    rng = np.random.default_rng(0)
    out = []
    for u in range(4):
        out.append(
            ProtocolSplit(
                subject=f"u{u}",
                train=rng.normal(0, 1, (30, 3)),
                genuine=rng.normal(0, 1, (20, 3)),
                impostor=rng.normal(separation, 1, (20, 3)),
            )
        )
    return out


def test_well_separated_users_have_zero_eer():
    rows = evaluate_splits(_splits(50.0), ScaledManhattan)
    assert [r["subject"] for r in rows] == ["u0", "u1", "u2", "u3"]
    assert all(r["eer"] == 0.0 and r["roc_auc"] == 1.0 for r in rows)
    assert rows[0]["n_train"] == 30 and rows[0]["n_genuine"] == 20 and rows[0]["n_impostor"] == 20


def test_summary_reports_mean_sd_and_ci():
    rows = [{"eer": v, "roc_auc": 1 - v} for v in (0.1, 0.2, 0.3)]
    s = summarise(rows, seed=0)
    assert s["n_users"] == 3
    assert s["eer_mean"] == pytest.approx(0.2)
    assert s["eer_sd"] == pytest.approx(0.1)  # sample standard deviation
    assert s["eer_ci95"][0] <= 0.2 <= s["eer_ci95"][1]
    assert s["roc_auc_mean"] == pytest.approx(0.8)
