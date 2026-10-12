"""P1-3: the privacy cost of key categories (proposal Section 13).

Usage (from the repository root, after fetching the Aalto subset):
    .venv/Scripts/python -m ml.datasets.aalto --n 500 --seed 0
    .venv/Scripts/python -m experiments.category_vs_keypair

Compares, with the same detectors and protocol, keystroke features that know
only key categories (``kf-1``, what the live system uses) against features
that know key identities.

CMU (fixed password, Killourhy and Maxion standard protocol):
- key-pair variant: the 31 published per-key timing features;
- category variant: ``kf-1`` computed from the eleven presses rebuilt from
  those columns.

Aalto (transcription typing, a seeded subset of participants):
- each participant's presses in typing order are cut into non-overlapping
  windows of 50 presses, the live window size;
- participants with at least 8 windows are kept; the first half of a
  participant's windows trains the detector, the second half is the genuine
  test, and the first window of every other kept participant is the impostor
  test;
- key-pair variant: ``ml.keypair.extract_keypair``; category variant: ``kf-1``.

For each dataset and detector the script reports mean per-user EER and ROC-AUC
with 95% percentile bootstrap intervals over users (2000 resamples, seed 0),
and the paired per-user EER difference (category minus key-pair) with its own
bootstrap interval. A positive difference is the accuracy cost of privacy.
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

from ml.datasets.aalto import DEFAULT_DIR as AALTO_DIR
from ml.datasets.aalto import load_subset
from ml.datasets.cmu import CMUData, ProtocolSplit, load_cmu, presses_from_row, standard_protocol
from ml.evaluation import evaluate_splits, summarise
from ml.keypair import KP1_NAMES, extract_category, extract_keypair
from ml.metrics import bootstrap_ci
from ml.models import GaussianMixtureModel, IsolationForestModel, OneClassSVMModel, ScaledManhattan
from server.features.schemas import KF1_NAMES

CMU_FILE = Path("data/cmu/DSL-StrongPasswordData.csv")
OUT = Path("experiments/results")
SEED = 0
WINDOW = 50
MIN_WINDOWS = 8

DETECTORS = {
    "scaled_manhattan": lambda: ScaledManhattan(),
    "ocsvm": lambda: OneClassSVMModel(),
    "gmm": lambda: GaussianMixtureModel(seed=SEED),
    "isolation_forest": lambda: IsolationForestModel(seed=SEED),
}


def cmu_variants() -> tuple[dict, dict]:
    data = load_cmu(CMU_FILE)
    cat = np.array([extract_category(presses_from_row(row, data.feature_names))[1] for row in data.X])
    variants = {
        "keypair": data,
        "category": CMUData(subjects=data.subjects, feature_names=KF1_NAMES, X=cat, subject=data.subject),
    }
    info = {
        "file": str(CMU_FILE).replace("\\", "/"),
        "sha256": hashlib.sha256(CMU_FILE.read_bytes()).hexdigest(),
        "n_users": len(data.subjects),
        "n_rows": int(data.X.shape[0]),
        "n_features": {"keypair": data.X.shape[1], "category": cat.shape[1]},
    }
    return variants, info


def aalto_windows() -> tuple[dict[str, dict[str, np.ndarray]], dict]:
    participants = load_subset(AALTO_DIR)
    feats: dict[str, dict[str, np.ndarray]] = {"category": {}, "keypair": {}}
    skipped_windows = 0
    for pid, presses in participants.items():
        cat_rows, kp_rows = [], []
        for start in range(0, len(presses) - WINDOW + 1, WINDOW):
            window = presses[start : start + WINDOW]
            try:
                cat_rows.append(extract_category(window)[1])
                kp_rows.append(extract_keypair(window))
            except ValueError:
                skipped_windows += 1
        if len(cat_rows) >= MIN_WINDOWS:
            feats["category"][pid] = np.asarray(cat_rows, dtype=float)
            feats["keypair"][pid] = np.asarray(kp_rows, dtype=float)
    manifest = (AALTO_DIR / "subset.json").read_bytes()
    kept = sorted(feats["category"])
    info = {
        "source": json.loads(manifest)["source"],
        "subset_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "n_participants_fetched": len(participants),
        "n_users_kept": len(kept),
        "window_presses": WINDOW,
        "min_windows": MIN_WINDOWS,
        "n_windows": int(sum(feats["category"][p].shape[0] for p in kept)),
        "n_windows_skipped": skipped_windows,
        "n_features": {"keypair": len(KP1_NAMES), "category": len(KF1_NAMES)},
    }
    return feats, info


def aalto_splits(per_user: dict[str, np.ndarray]):
    users = sorted(per_user)
    for u in users:
        rows = per_user[u]
        half = rows.shape[0] // 2
        impostor = np.vstack([per_user[o][:1] for o in users if o != u])
        yield ProtocolSplit(subject=u, train=rows[:half], genuine=rows[half:], impostor=impostor)


def compare(make_splits, variants: list[str]) -> dict:
    out: dict = {}
    for name, factory in DETECTORS.items():
        entry: dict = {}
        per_user: dict[str, dict[str, float]] = {}
        for variant in variants:
            start = time.perf_counter()
            rows = evaluate_splits(make_splits(variant), factory)
            entry[variant] = {"summary": summarise(rows, seed=SEED), "seconds": round(time.perf_counter() - start, 1)}
            per_user[variant] = {r["subject"]: r["eer"] for r in rows}
        diffs = np.array([per_user["category"][u] - per_user["keypair"][u] for u in sorted(per_user["category"])])
        entry["eer_cost_category_minus_keypair"] = {
            "mean": float(diffs.mean()),
            "ci95": list(bootstrap_ci(diffs, seed=SEED)),
        }
        out[name] = entry
        c, k, d = entry["category"]["summary"], entry["keypair"]["summary"], entry["eer_cost_category_minus_keypair"]
        print(f"  {name:18s} keypair EER {k['eer_mean']:.4f}  category EER {c['eer_mean']:.4f}  cost {d['mean']:+.4f}")
    return out


def main() -> None:
    results: dict = {
        "experiment": "category_vs_keypair",
        "command": "python -m experiments.category_vs_keypair",
        "seed": SEED,
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "platform": platform.platform(),
        },
        "datasets": {},
        "results": {},
    }
    print("CMU")
    cmu, info = cmu_variants()
    results["datasets"]["cmu"] = info
    results["results"]["cmu"] = compare(lambda v: standard_protocol(cmu[v]), ["keypair", "category"])

    print("Aalto")
    feats, info = aalto_windows()
    results["datasets"]["aalto"] = info
    results["results"]["aalto"] = compare(lambda v: aalto_splits(feats[v]), ["keypair", "category"])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "category_vs_keypair.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "category_vs_keypair.md").write_text(render(results), encoding="utf-8")


def _ci(x: list[float]) -> str:
    return f"[{x[0]:.4f}, {x[1]:.4f}]"


def render(results: dict) -> str:
    cmu, aalto = results["datasets"]["cmu"], results["datasets"]["aalto"]
    lines = [
        "# Privacy cost of key categories (P1-3)",
        "",
        f"Command: `{results['command']}`. Seed {results['seed']}. "
        f"Python {results['environment']['python']}, numpy {results['environment']['numpy']}, "
        f"scikit-learn {results['environment']['scikit_learn']}.",
        "",
        "The live system sees only key categories (`kf-1`). This experiment measures the cost of that choice by "
        "comparing it with features that know which key was pressed, using the same detectors and protocol. "
        "The cost column is the mean per-user EER difference, category minus key-pair, with a paired percentile "
        "bootstrap interval over users (2000 resamples). A positive cost means categories are less accurate.",
        "",
        "## Datasets",
        "",
        f"- CMU: `{cmu['file']}` (SHA-256 `{cmu['sha256']}`), {cmu['n_users']} users, {cmu['n_rows']} repetitions. "
        f"Key-pair variant: the {cmu['n_features']['keypair']} published per-key features. Category variant: "
        f"`kf-1` ({cmu['n_features']['category']} features) from the rebuilt presses. Standard protocol "
        "(train 200, genuine 200, impostor 5 repetitions from each other user).",
        f"- Aalto 136M keystrokes: seeded subset of {aalto['n_participants_fetched']} participants from "
        f"{aalto['source']} (manifest SHA-256 `{aalto['subset_manifest_sha256']}`). Non-overlapping windows of "
        f"{aalto['window_presses']} presses; {aalto['n_users_kept']} users with at least {aalto['min_windows']} "
        f"windows kept, {aalto['n_windows']} windows in total ({aalto['n_windows_skipped']} skipped as invalid). "
        "First half of each user's windows trains, second half is genuine, the first window of every other user "
        f"is impostor. Key-pair variant: {aalto['n_features']['keypair']} features (`ml/keypair.py`); "
        f"category variant: `kf-1` ({aalto['n_features']['category']} features).",
        "",
    ]
    for ds, title in (("cmu", "CMU"), ("aalto", "Aalto")):
        lines += [
            f"## {title}",
            "",
            "| Detector | Key-pair EER [95% CI] | Category EER [95% CI] | Cost (category minus key-pair) [95% CI] | "
            "Key-pair AUC | Category AUC |",
            "|---|---|---|---|---|---|",
        ]
        for name, e in results["results"][ds].items():
            k, c, d = e["keypair"]["summary"], e["category"]["summary"], e["eer_cost_category_minus_keypair"]
            lines.append(
                f"| {name} | {k['eer_mean']:.4f} {_ci(k['eer_ci95'])} | {c['eer_mean']:.4f} {_ci(c['eer_ci95'])} | "
                f"{d['mean']:+.4f} {_ci(d['ci95'])} | {k['roc_auc_mean']:.4f} | {c['roc_auc_mean']:.4f} |"
            )
        lines.append("")
    lines += [
        "## Limits",
        "",
        "- CMU is one fixed password, so its key-pair variant is the strongest possible case for key identity.",
        "- Aalto participants transcribe given sentences; this is closer to free text than CMU but is not the "
        "composed free text the live system sees.",
        "- Aalto users here have few training windows (half of at least eight), so absolute EERs are higher than "
        "with a longer enrollment. The comparison between variants is paired and uses identical windows.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
