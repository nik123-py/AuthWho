"""How close the synthetic cohort is to real behaviour (ml/synthetic.py).

Usage (after generating data/synthetic and fetching the public datasets):
    .venv/Scripts/python -m experiments.synthetic_calibration

Computes the same live window features on the synthetic cohort, on the Aalto
subset (typing) and on SapiMouse (pointer), and reports the 10th, 50th and
90th percentiles side by side, plus the share of synthetic windows the bot
checks flag. Writes experiments/results/synthetic_calibration.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from experiments.category_vs_keypair import aalto_windows
from experiments.pointer_baselines import featurise
from ml.datasets.mouse import load_sapimouse
from ml.synthetic import load_session
from server.features.keystroke import extract_keystroke
from server.features.pointer import PointerWindower, extract_pointer, segment_strokes
from server.features.schemas import KF1_NAMES, PF1_NAMES
from server.features.windowing import KeystrokeWindower
from server.policy.bots import check_window

DATA = Path("data/synthetic")
OUT = Path("experiments/results")
KS = ["dwell_mean", "flight_median", "dd_median", "rollover_rate", "correction_rate", "typing_rate", "pause_rate"]
PT = ["velocity_mean", "efficiency_mean", "curvature_mean", "duration_mean", "click_rate", "pre_click_pause_mean"]


def _pct(col):
    return [float(np.percentile(col, q)) for q in (10, 50, 90)]


def main() -> None:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    kv, pv, flagged = [], [], 0
    for u in manifest["users"]:
        for s in u["sessions"]:
            ev = load_session(DATA / u["user_id"] / s["file"])
            for w in KeystrokeWindower(stride=50).add(ev):
                v = extract_keystroke(w).values
                kv.append(v)
                flagged += bool(check_window("keystroke", KF1_NAMES, v))
            for w in PointerWindower(stride=30).add(ev):
                v = extract_pointer(w).values
                pv.append(v)
                flagged += bool(check_window("pointer", PF1_NAMES, v))
    kv, pv = np.array(kv), np.array(pv)
    feats, _ = aalto_windows()
    real_k = np.vstack(list(feats["category"].values()))
    mats = [featurise(segment_strokes(d["3min"]), 30, 30) for d in load_sapimouse().values()]
    real_p = np.vstack([m for m in mats if m.shape[0]])

    lines = [
        "# Synthetic cohort calibration",
        "",
        f"Synthetic cohort: {manifest['n_users']} users, seed {manifest['seed']}, "
        f"{sum(len(u['sessions']) for u in manifest['users'])} sessions; {len(kv)} keystroke and {len(pv)} pointer "
        f"windows (non-overlapping). Real references: Aalto subset ({len(real_k)} keystroke windows) and SapiMouse "
        f"3-minute sessions ({len(real_p)} pointer windows). Values are p10 / median / p90 of the live window features.",
        "",
        f"Bot checks flagged {flagged} of {len(kv) + len(pv)} synthetic windows.",
        "",
        "| Feature | Synthetic | Real |",
        "|---|---|---|",
    ]
    for name in KS:
        i = KF1_NAMES.index(name)
        s, r = _pct(kv[:, i]), _pct(real_k[:, i])
        lines.append(f"| {name} | {s[0]:.3g} / {s[1]:.3g} / {s[2]:.3g} | {r[0]:.3g} / {r[1]:.3g} / {r[2]:.3g} |")
    for name in PT:
        i = PF1_NAMES.index(name)
        s, r = _pct(pv[:, i]), _pct(real_p[:, i])
        lines.append(f"| {name} | {s[0]:.3g} / {s[1]:.3g} / {s[2]:.3g} | {r[0]:.3g} / {r[1]:.3g} / {r[2]:.3g} |")
    lines += [
        "",
        "Known differences: synthetic pointer strokes are shorter and end in a click less often than SapiMouse "
        "strokes, because SapiMouse is a click-the-target task while the synthetic sessions model web browsing "
        "and form filling. Synthetic results must be read as a test of the pipeline and method, not as "
        "measurements of real people.",
        "",
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "synthetic_calibration.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
