"""CMU keystroke benchmark on the Killourhy and Maxion (2009) standard protocol.

Usage (from the repository root):
    .venv/Scripts/python -m experiments.cmu_standard_protocol

Reads data/cmu/DSL-StrongPasswordData.csv and writes
experiments/results/cmu_standard_protocol.json and .md. Every detector uses
its default settings in ml.models and seed 0; the bootstrap interval over the
51 users uses seed 0 and 2000 resamples.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import sklearn

from ml.datasets.cmu import load_cmu, standard_protocol
from ml.evaluation import evaluate_splits, summarise
from ml.models import GaussianMixtureModel, IsolationForestModel, OneClassSVMModel, ScaledManhattan

DATA = Path("data/cmu/DSL-StrongPasswordData.csv")
OUT = Path("experiments/results")
SEED = 0
PUBLISHED_SCALED_MANHATTAN = {"eer_mean": 0.096, "eer_sd": 0.069}

DETECTORS = {
    "scaled_manhattan": lambda: ScaledManhattan(),
    "ocsvm": lambda: OneClassSVMModel(),
    "gmm": lambda: GaussianMixtureModel(seed=SEED),
    "isolation_forest": lambda: IsolationForestModel(seed=SEED),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    data = load_cmu(DATA)
    results = {
        "experiment": "cmu_standard_protocol",
        "command": "python -m experiments.cmu_standard_protocol",
        "dataset": {
            "file": str(DATA).replace("\\", "/"),
            "sha256": sha256(DATA),
            "n_subjects": len(data.subjects),
            "n_rows": int(data.X.shape[0]),
            "n_features": len(data.feature_names),
        },
        "protocol": {"n_train": 200, "n_genuine_test": 200, "n_impostor_reps_per_other_subject": 5},
        "seed": SEED,
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "platform": platform.platform(),
        },
        "published_baseline": {"source": "Killourhy and Maxion 2009, scaled Manhattan", **PUBLISHED_SCALED_MANHATTAN},
        "detectors": {},
    }
    for name, factory in DETECTORS.items():
        start = time.perf_counter()
        rows = evaluate_splits(standard_protocol(data), factory)
        results["detectors"][name] = {
            "summary": summarise(rows, seed=SEED),
            "seconds": round(time.perf_counter() - start, 1),
            "per_user": rows,
        }
        s = results["detectors"][name]["summary"]
        print(f"{name:18s} EER {s['eer_mean']:.4f} (sd {s['eer_sd']:.4f}) AUC {s['roc_auc_mean']:.4f}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cmu_standard_protocol.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "cmu_standard_protocol.md").write_text(render(results), encoding="utf-8")


def render(results: dict) -> str:
    d = results["dataset"]
    lines = [
        "# CMU keystroke benchmark, standard protocol",
        "",
        f"Command: `{results['command']}`. Dataset `{d['file']}` (SHA-256 `{d['sha256']}`), "
        f"{d['n_subjects']} subjects, {d['n_rows']} rows, {d['n_features']} features. Seed {results['seed']}.",
        "",
        "Protocol (Killourhy and Maxion 2009): per subject, train on the first 200 repetitions, test on the "
        "remaining 200 and on the first 5 repetitions of each of the other 50 subjects. EER and ROC-AUC are "
        "computed per subject and averaged; the 95% interval is a percentile bootstrap over subjects "
        "(2000 resamples).",
        "",
        "| Detector | Mean EER | SD | 95% CI of mean EER | Mean ROC-AUC | 95% CI of mean AUC |",
        "|---|---|---|---|---|---|",
    ]
    for name, r in results["detectors"].items():
        s = r["summary"]
        lines.append(
            f"| {name} | {s['eer_mean']:.4f} | {s['eer_sd']:.4f} | "
            f"[{s['eer_ci95'][0]:.4f}, {s['eer_ci95'][1]:.4f}] | {s['roc_auc_mean']:.4f} | "
            f"[{s['roc_auc_ci95'][0]:.4f}, {s['roc_auc_ci95'][1]:.4f}] |"
        )
    p = results["published_baseline"]
    lines += [
        f"| Published: {p['source']} | {p['eer_mean']:.3f} | {p['eer_sd']:.3f} | not reported | not reported | |",
        "",
        "Note: EER here is interpolated linearly at the FAR and FRR crossing (see `ml/metrics.py`). "
        "Detector settings are the defaults in `ml/models/`, which are not identical to the paper's "
        "(for example the One-Class SVM here z-scores features and uses nu = 0.05).",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
