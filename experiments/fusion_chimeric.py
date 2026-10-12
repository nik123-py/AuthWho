"""P3 indicative evaluation: fusion and trust on chimeric users.

Usage (from the repository root, after the Aalto subset and SapiMouse are in data/):
    .venv/Scripts/python -m experiments.fusion_chimeric

No public dataset has keyboard and mouse data from the same people, so this
uses chimeric users, a standard practice in multimodal biometrics: each of the
120 SapiMouse users is paired with a seeded random Aalto participant, treating
the two channels as independent. This is indicative only. The proposal's P3
criterion ("fused score beats each single channel on volunteer data") needs
the consented volunteer dataset, which is not collected yet.

Everything runs through the live runtime code: ``kf-1`` and ``pf-1`` window
features, ``ml.profile`` templates with per-user calibration, and
``ml.trust.TrustEngine``.

Per chimeric user:
- keystroke: Aalto windows of 50 presses; the first half enrol, the rest are
  genuine tests;
- pointer: SapiMouse windows of 30 strokes; the 3-minute session enrols
  (stride 15), the 1-minute session's windows (stride 15) are genuine tests.

1. Score fusion. An attempt is one keystroke window plus one pointer window
   (roughly a minute of active use). Genuine attempts pair the user's genuine
   test windows; impostor attempts take one attempt from each of 50 other
   chimeric users (seeded). Single-channel scores use the same attempts. The
   fused score is the mean of the two calibrated scores. Per-user EER and AUC
   are averaged over users with 95% bootstrap intervals; the paired EER
   difference (fused minus best single channel per user) has its own interval.
2. Trust simulation. The user's genuine test windows, alternating channels,
   feed a fresh TrustEngine; a false step-up is any trust value below 50.
   For impostors, the first windows of 20 other chimeric users feed an engine
   for this user's templates; time to detect is the number of windows until
   trust falls below 50 (or "not detected" within the windows available).
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

import numpy as np
import sklearn

from experiments.category_vs_keypair import aalto_windows
from experiments.pointer_baselines import featurise
from ml.datasets.mouse import load_sapimouse
from ml.metrics import bootstrap_ci, eer, roc_auc
from ml.profile import score_window, train_template
from ml.trust import TrustEngine
from server.features.pointer import segment_strokes
from server.features.schemas import KF1_NAMES, PF1_NAMES

OUT = Path("experiments/results")
SEED = 0
N_IMPOSTOR_ATTEMPTS = 50
N_IMPOSTOR_STREAMS = 20
SWEEP = [(0.2, 8, 5), (0.2, 10, 5), (0.25, 8, 5), (0.25, 10, 5), (0.25, 12, 5), (0.15, 10, 5), (0.3, 12, 5)]


def build_users():
    rng = np.random.default_rng(SEED)
    feats, _ = aalto_windows()
    ks_users = sorted(feats["category"])
    sapi = load_sapimouse()
    users = []
    sapi_ids = sorted(u for u in sapi if "3min" in sapi[u] and "1min" in sapi[u])
    aalto_pick = rng.choice(len(ks_users), size=len(sapi_ids), replace=False)
    for sid, ai in zip(sapi_ids, aalto_pick):
        k = feats["category"][ks_users[ai]]
        half = k.shape[0] // 2
        p_enrol = featurise(segment_strokes(sapi[sid]["3min"]), 30, 15)
        p_test = featurise(segment_strokes(sapi[sid]["1min"]), 30, 15)
        if p_enrol.shape[0] < 5 or p_test.shape[0] < 1:
            continue
        users.append({
            "id": f"{sid}+aalto{ks_users[ai]}",
            "kt": train_template("keystroke", "kf-1", KF1_NAMES, k[:half], [1.0] * half),
            "pt": train_template("pointer", "pf-1", PF1_NAMES, p_enrol, [1.0] * p_enrol.shape[0]),
            "k_test": k[half:],
            "p_test": p_test,
        })
    return users


def s(template, x) -> float:
    return score_window(template, x, quality=1.0)["score"]


def fusion(users) -> dict:
    rng = np.random.default_rng(SEED)
    rows = []
    for idx, u in enumerate(users):
        others = [o for j, o in enumerate(users) if j != idx]
        pick = rng.choice(len(others), size=min(N_IMPOSTOR_ATTEMPTS, len(others)), replace=False)
        g = [(s(u["kt"], k), s(u["pt"], u["p_test"][i % len(u["p_test"])])) for i, k in enumerate(u["k_test"])]
        im = [(s(u["kt"], others[j]["k_test"][0]), s(u["pt"], others[j]["p_test"][0])) for j in pick]
        g, im = np.array(g), np.array(im)
        row = {"subject": u["id"], "n_genuine": len(g), "n_impostor": len(im)}
        for name, gs, is_ in (("keystroke", g[:, 0], im[:, 0]), ("pointer", g[:, 1], im[:, 1]),
                              ("fused", g.mean(axis=1), im.mean(axis=1))):
            row[f"{name}_eer"], row[f"{name}_auc"] = eer(gs, is_), roc_auc(gs, is_)
        rows.append(row)
    out = {"n_users": len(rows), "per_user": rows}
    for name in ("keystroke", "pointer", "fused"):
        e = np.array([r[f"{name}_eer"] for r in rows])
        a = np.array([r[f"{name}_auc"] for r in rows])
        out[name] = {"eer_mean": float(e.mean()), "eer_ci95": list(bootstrap_ci(e, seed=SEED)),
                     "auc_mean": float(a.mean()), "auc_ci95": list(bootstrap_ci(a, seed=SEED))}
    best = np.array([min(r["keystroke_eer"], r["pointer_eer"]) for r in rows])
    diff = np.array([r["fused_eer"] for r in rows]) - best
    out["fused_minus_best_single"] = {"mean": float(diff.mean()), "ci95": list(bootstrap_ci(diff, seed=SEED))}
    for name in ("keystroke", "pointer"):
        d = np.array([r["fused_eer"] - r[f"{name}_eer"] for r in rows])
        out[f"fused_minus_{name}"] = {"mean": float(d.mean()), "ci95": list(bootstrap_ci(d, seed=SEED))}
    return out


def _stream(engine, kt, pt, k_rows, p_rows, limit=None):
    """Alternate keystroke and pointer windows; return the trust after each window."""
    trusts, ki, pi, t = [], 0, 0, 0.0
    while (ki < len(k_rows) or pi < len(p_rows)) and (limit is None or len(trusts) < limit):
        if ki < len(k_rows) and (pi >= len(p_rows) or ki <= pi):
            r = score_window(kt, k_rows[ki], 1.0)
            u = engine.update("keystroke", {**r, "window_id": None}, now=t)
            ki += 1
        else:
            r = score_window(pt, p_rows[pi], 1.0)
            u = engine.update("pointer", {**r, "window_id": None}, now=t)
            pi += 1
        trusts.append(u["trust"])
        t += 15.0
    return trusts


def trust_simulation(users, thresholds=(75.0, 50.0)) -> dict:
    """Genuine false step-ups and impostor time to detect at each trust threshold."""
    rng = np.random.default_rng(SEED + 1)
    genuine_min, genuine_windows, impostor_traces = [], 0, []
    for idx, u in enumerate(users):
        g = _stream(TrustEngine("g", u["id"], now=0.0), u["kt"], u["pt"], u["k_test"], u["p_test"])
        genuine_windows += len(g)
        genuine_min.append(min(g))
        others = [o for j, o in enumerate(users) if j != idx]
        for j in rng.choice(len(others), size=min(N_IMPOSTOR_STREAMS, len(others)), replace=False):
            o = others[j]
            impostor_traces.append(
                _stream(TrustEngine("i", u["id"], now=0.0), u["kt"], u["pt"], o["k_test"][:6], o["p_test"][:6]))
    out = {"genuine_users": len(users), "genuine_windows": genuine_windows,
           "genuine_min_trust_median": float(np.median(genuine_min)),
           "impostor_streams": len(impostor_traces), "thresholds": {}}
    for th in thresholds:
        first = [next((n for n, v in enumerate(tr, start=1) if v < th), None) for tr in impostor_traces]
        d = np.array([f for f in first if f is not None])
        false = sum(m < th for m in genuine_min)
        out["thresholds"][str(int(th))] = {
            "genuine_users_below": int(false),
            "genuine_rate_below": false / len(users),
            "impostor_detected_rate": float(d.size / len(first)),
            "time_to_detect_windows_median": float(np.median(d)) if d.size else None,
            "time_to_detect_windows_p90": float(np.percentile(d, 90)) if d.size else None,
        }
    return out


def main() -> None:
    users = build_users()
    print(f"chimeric users: {len(users)}")
    fu = fusion(users)
    for name in ("keystroke", "pointer", "fused"):
        print(f"  {name:10s} EER {fu[name]['eer_mean']:.4f} {fu[name]['eer_ci95']}  AUC {fu[name]['auc_mean']:.4f}")
    print(f"  fused minus best single per user: {fu['fused_minus_best_single']}")
    tr = trust_simulation(users)
    print("  trust:", json.dumps(tr["thresholds"]))
    import ml.trust as trust_module
    chosen = (trust_module.TAU, trust_module.PENALTY, trust_module.REWARD)
    sweep = []
    for tau, pen, rew in SWEEP:
        trust_module.TAU, trust_module.PENALTY, trust_module.REWARD = tau, pen, rew
        sweep.append({"tau": tau, "penalty": pen, "reward": rew, **trust_simulation(users)["thresholds"]})
    trust_module.TAU, trust_module.PENALTY, trust_module.REWARD = chosen
    tr["chosen"] = {"tau": chosen[0], "penalty": chosen[1], "reward": chosen[2]}
    tr["sweep"] = sweep
    results = {
        "experiment": "fusion_chimeric",
        "command": "python -m experiments.fusion_chimeric",
        "seed": SEED,
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__,
                        "scikit_learn": sklearn.__version__, "platform": platform.platform()},
        "fusion": fu,
        "trust": tr,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fusion_chimeric.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "fusion_chimeric.md").write_text(render(results), encoding="utf-8")


def _ci(x) -> str:
    return f"[{x[0]:.4f}, {x[1]:.4f}]"


def render(r: dict) -> str:
    fu, tr = r["fusion"], r["trust"]
    lines = [
        "# Fusion and trust on chimeric users (P3, indicative)",
        "",
        f"Command: `{r['command']}`. Seed {r['seed']}. Python {r['environment']['python']}, "
        f"numpy {r['environment']['numpy']}, scikit-learn {r['environment']['scikit_learn']}.",
        "",
        "**This is not the P3 success criterion.** The proposal asks for fusion to beat each single channel on the "
        "consented volunteer dataset, which is not collected yet. No public dataset has keyboard and mouse data from "
        "the same people, so each SapiMouse user is paired with a seeded random Aalto participant (a chimeric user), "
        "which assumes the two channels are independent. All scoring uses the live runtime code (`kf-1`, `pf-1`, "
        "`ml/profile.py`, `ml/trust.py`). See the docstring of `experiments/fusion_chimeric.py` for the protocol.",
        "",
        f"## Score fusion ({fu['n_users']} chimeric users)",
        "",
        "An attempt is one 50-press keystroke window plus one 30-stroke pointer window. Mean per-user values with "
        "95% bootstrap intervals over users.",
        "",
        "| Score | Mean EER [95% CI] | Mean ROC-AUC [95% CI] |",
        "|---|---|---|",
    ]
    for name in ("keystroke", "pointer", "fused"):
        lines.append(f"| {name} | {fu[name]['eer_mean']:.4f} {_ci(fu[name]['eer_ci95'])} | "
                     f"{fu[name]['auc_mean']:.4f} {_ci(fu[name]['auc_ci95'])} |")
    lines += [
        "",
        f"- Fused minus keystroke EER: {fu['fused_minus_keystroke']['mean']:+.4f} {_ci(fu['fused_minus_keystroke']['ci95'])}",
        f"- Fused minus pointer EER: {fu['fused_minus_pointer']['mean']:+.4f} {_ci(fu['fused_minus_pointer']['ci95'])}",
        f"- Fused minus the better single channel per user (an oracle choice): "
        f"{fu['fused_minus_best_single']['mean']:+.4f} {_ci(fu['fused_minus_best_single']['ci95'])}",
        "",
        "## Trust simulation",
        "",
        f"Genuine streams: {tr['genuine_users']} users, {tr['genuine_windows']} windows in total (the user's own "
        f"test windows, alternating channels); median of each user's minimum trust {tr['genuine_min_trust_median']:.1f}. "
        f"Impostor streams: {tr['impostor_streams']} (another chimeric user's first 6 keystroke and 6 pointer "
        "windows against this user's templates). Trust below 75 means moderate deviation (step-up before "
        "high-risk actions); below 50 means strong deviation (step-up before continuing).",
        "",
        "| Threshold | Genuine users ever below | Impostor streams detected within 12 windows | Windows to detect, median | 90th percentile |",
        "|---|---|---|---|---|",
        *[f"| {th} | {v['genuine_users_below']} ({v['genuine_rate_below']:.3f}) | {v['impostor_detected_rate']:.3f} | "
          f"{v['time_to_detect_windows_median']} | {v['time_to_detect_windows_p90']} |" for th, v in tr["thresholds"].items()],
        "",
        f"Chosen settings: TAU {tr['chosen']['tau']}, PENALTY {tr['chosen']['penalty']}, REWARD {tr['chosen']['reward']} "
        "(ruling R13): the most impostor detection while keeping genuine users below 50 at about 2% of streams or "
        "fewer. The sweep below was run on the same chimeric data, so the chosen setting's numbers are optimistic.",
        "",
        "| TAU | PENALTY | REWARD | Genuine below 75 | Impostors below 75 | Genuine below 50 | Impostors below 50 |",
        "|---|---|---|---|---|---|---|",
        *[f"| {w['tau']} | {w['penalty']} | {w['reward']} | {w['75']['genuine_users_below']} | "
          f"{w['75']['impostor_detected_rate']:.3f} | {w['50']['genuine_users_below']} | {w['50']['impostor_detected_rate']:.3f} |"
          for w in tr["sweep"]],
        "",
        "## Limits",
        "",
        "- Chimeric pairing assumes independence between a person's typing and mouse behaviour.",
        "- Genuine test data per user is small (about 6 keystroke and 2 pointer windows), so the genuine false "
        "step-up rate is measured over short streams and is not a per-hour friction figure.",
        "- Genuine pointer tests come from SapiMouse's 1-minute session, recorded right after enrollment, so drift "
        "across days is not covered.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
