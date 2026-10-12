"""P2-2: per-user pointer models on public mouse datasets (proposal Section 14).

Usage (from the repository root, with the archives in data/balabit and
data/sapimouse; see ml/datasets/mouse.py for the official sources):
    .venv/Scripts/python -m experiments.pointer_baselines

Features are the live ``pf-1`` vector over windows of strokes, produced by the
same code the worker runs (``server/features/pointer.py``).

Balabit (10 users):
- train: windows of 30 strokes, stride 15, from the user's training sessions
  (at most the first 400 windows per user);
- test: every labelled test session in the user's folder with at least one
  30-stroke window; a session's score is the mean of its non-overlapping
  window scores; genuine and impostor come from ``public_labels.csv``.

SapiMouse (120 users), for windows of 30 strokes (the live size) and 10:
- train: the 3-minute session, windows with half-window stride;
- genuine: the non-overlapping windows of the user's 1-minute session;
- impostor: the first window of every other user's 1-minute session.
Users whose 1-minute session is shorter than one window are left out.

Each detector is fitted per user. Mean per-user EER and ROC-AUC are reported
with 95% percentile bootstrap intervals over users (2000 resamples, seed 0).
All participants are treated as mouse users: neither dataset labels which
sessions used a touchpad, so touchpad results need the volunteer dataset.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sklearn

from ml.datasets.mouse import BALABIT_URL, BALABIT_ZIP, SAPIMOUSE_URL, SAPIMOUSE_ZIP, load_balabit, load_sapimouse, windows_of
from ml.evaluation import summarise
from ml.metrics import eer, roc_auc
from ml.models import GaussianMixtureModel, IsolationForestModel, OneClassSVMModel, ScaledManhattan
from server.features.pointer import extract_pointer, segment_strokes

OUT = Path("experiments/results")
SEED = 0
BALABIT_MAX_TRAIN_WINDOWS = 400

DETECTORS = {
    "scaled_manhattan": lambda: ScaledManhattan(),
    "ocsvm": lambda: OneClassSVMModel(),
    "gmm": lambda: GaussianMixtureModel(seed=SEED),
    "isolation_forest": lambda: IsolationForestModel(seed=SEED),
}


def featurise(strokes, size: int, stride: int | None = None) -> np.ndarray:
    rows = [extract_pointer(w).values for w in windows_of(strokes, size, stride)]
    if not rows:
        return np.empty((0, 0))
    return np.asarray(rows, dtype=float)


@dataclass
class SessionSplit:
    subject: str
    train: np.ndarray
    genuine: list[np.ndarray]  # each a session's window matrix
    impostor: list[np.ndarray]


def balabit_splits() -> list[SessionSplit]:
    data = load_balabit()
    splits = []
    for user in sorted(data["train"]):
        strokes = [st for session in data["train"][user] for st in segment_strokes(session)]
        train = featurise(strokes, 30, 15)[:BALABIT_MAX_TRAIN_WINDOWS]
        genuine, impostor = [], []
        for label, samples in data["test"].get(user, []):
            win = featurise(segment_strokes(samples), 30)
            if win.shape[0]:
                (impostor if label else genuine).append(win)
        splits.append(SessionSplit(user, train, genuine, impostor))
    return splits


def sapimouse_splits(size: int) -> list[SessionSplit]:
    data = load_sapimouse()
    one_min = {u: featurise(segment_strokes(d["1min"]), size) for u, d in data.items() if "1min" in d}
    users = sorted(u for u in data if "3min" in data[u] and one_min.get(u) is not None and one_min[u].shape[0])
    splits = []
    for u in users:
        train = featurise(segment_strokes(data[u]["3min"]), size, max(1, size // 2))
        genuine = [one_min[u][i : i + 1] for i in range(one_min[u].shape[0])]
        impostor = [one_min[o][:1] for o in users if o != u]
        splits.append(SessionSplit(u, train, genuine, impostor))
    return splits


def evaluate(splits: list[SessionSplit], factory) -> list[dict]:
    rows = []
    for s in splits:
        if s.train.shape[0] < 2 or not s.genuine or not s.impostor:
            continue
        model = factory().fit(s.train)
        g = np.array([model.score(w).mean() for w in s.genuine])
        i = np.array([model.score(w).mean() for w in s.impostor])
        rows.append({"subject": s.subject, "n_train": int(s.train.shape[0]), "n_genuine": int(g.size),
                     "n_impostor": int(i.size), "eer": eer(g, i), "roc_auc": roc_auc(g, i)})
    return rows


def run(name: str, splits: list[SessionSplit]) -> dict:
    out = {"n_users": len(splits),
           "n_train_windows": int(sum(s.train.shape[0] for s in splits)),
           "n_genuine_tests": int(sum(len(s.genuine) for s in splits)),
           "detectors": {}}
    for det, factory in DETECTORS.items():
        start = time.perf_counter()
        rows = evaluate(splits, factory)
        out["detectors"][det] = {"summary": summarise(rows, seed=SEED), "seconds": round(time.perf_counter() - start, 1),
                                 "per_user": rows}
        s = out["detectors"][det]["summary"]
        print(f"  {name:12s} {det:18s} EER {s['eer_mean']:.4f}  AUC {s['roc_auc_mean']:.4f}  users {s['n_users']}")
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    results = {
        "experiment": "pointer_baselines",
        "command": "python -m experiments.pointer_baselines",
        "seed": SEED,
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__,
                        "scikit_learn": sklearn.__version__, "platform": platform.platform()},
        "datasets": {
            "balabit": {"source": BALABIT_URL, "sha256": sha256(BALABIT_ZIP)},
            "sapimouse": {"source": SAPIMOUSE_URL, "sha256": sha256(SAPIMOUSE_ZIP)},
        },
        "results": {},
    }
    print("Balabit")
    results["results"]["balabit_30"] = run("balabit_30", balabit_splits())
    for size in (30, 10):
        print(f"SapiMouse, {size}-stroke windows")
        results["results"][f"sapimouse_{size}"] = run(f"sapimouse_{size}", sapimouse_splits(size))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pointer_baselines.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "pointer_baselines.md").write_text(render(results), encoding="utf-8")


def render(results: dict) -> str:
    env = results["environment"]
    ds = results["datasets"]
    lines = [
        "# Pointer baselines on public mouse datasets (P2-2)",
        "",
        f"Command: `{results['command']}`. Seed {results['seed']}. Python {env['python']}, numpy {env['numpy']}, "
        f"scikit-learn {env['scikit_learn']}. Features: live `pf-1` (22 features) over windows of strokes.",
        "",
        f"- Balabit: `{ds['balabit']['source']}` (SHA-256 `{ds['balabit']['sha256']}`). Train on 30-stroke windows "
        f"(stride 15, at most {BALABIT_MAX_TRAIN_WINDOWS} per user) from training sessions; each labelled test "
        "session is scored by the mean of its 30-stroke windows; labels from `public_labels.csv`.",
        f"- SapiMouse: `{ds['sapimouse']['source']}` (SHA-256 `{ds['sapimouse']['sha256']}`). Train on the 3-minute "
        "session; genuine tests are the windows of the user's 1-minute session; impostor tests are the first window "
        "of every other user's 1-minute session.",
        "",
        "Mean per-user EER and ROC-AUC with 95% percentile bootstrap intervals over users (2000 resamples).",
        "",
        "| Setting | Users | Detector | Mean EER [95% CI] | Mean ROC-AUC [95% CI] |",
        "|---|---|---|---|---|",
    ]
    for setting, r in results["results"].items():
        for det, d in r["detectors"].items():
            s = d["summary"]
            lines.append(
                f"| {setting} | {s['n_users']} | {det} | {s['eer_mean']:.4f} [{s['eer_ci95'][0]:.4f}, "
                f"{s['eer_ci95'][1]:.4f}] | {s['roc_auc_mean']:.4f} [{s['roc_auc_ci95'][0]:.4f}, {s['roc_auc_ci95'][1]:.4f}] |"
            )
    lines += [
        "",
        "## Mouse and touchpad",
        "",
        "Both datasets are treated as mouse data. SapiMouse's authors note that some participants used a touchpad, "
        "but sessions are not labelled by device, so a separate touchpad result is **not measured** here. It needs "
        "the consented volunteer dataset, where the pointing device is recorded per session.",
        "",
        "## Limits",
        "",
        "- Balabit has only 10 users, so its interval is wide.",
        "- In SapiMouse each user's genuine test comes from a single one-minute session, so per-user EERs are coarse "
        "(few genuine windows), especially at 30 strokes.",
        "- Published SapiMouse results use deep features on short raw segments and are not directly comparable with "
        "these hand-crafted window features.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
