"""P6: every Section 13 core metric on the synthetic cohort, through the live code.

Usage (after ``python -m ml.synthetic``):
    .venv/Scripts/python -m experiments.synthetic_evaluation

SYNTHETIC DATA: the cohort comes from ml/synthetic.py (parameters fitted to
public data). These numbers test the system and the method end to end; they
are not measurements of real people and do not replace the volunteer study.

Protocol, mirroring the volunteer plan (6 sessions over at least 3 days):
- Windows are cut exactly as the worker does (keystroke 50 presses stride 25,
  pointer 30 strokes stride 15, interaction 20 events stride 10) and featurised
  with the live extractors.
- Enrollment: each user's sessions 1 and 2 train one template per channel
  (``ml.profile``). Tests use sessions 3 to 6, so they include day-to-day drift.
- Per-channel EER and ROC-AUC: genuine windows from the user's test sessions
  (every second window, so test windows do not overlap) against the same number
  of windows from other users' test sessions; pointer impostors use the same
  device type, and pointer results are reported for mouse and touchpad separately.
- Fusion (the P3 criterion's analogue): an attempt is a keystroke window and the
  pointer window nearest in time from the same session; the fused score is the
  mean of the two calibrated scores.
- Trust and policy: every test session streams through ``ml.trust`` and the
  policy rules in time order. Friction counts strong-deviation episodes (step-up
  before continuing) per hour of genuine use. Time to detect replays another
  user's session against the victim's templates, starting from full trust, and
  measures active seconds and actions until trust falls below 75 and below 50.
- Bots and replays: scripted constant-rhythm typing, straight constant-speed
  pointer movement, exact replays of stored windows, and replays with 1% jitter.
- Population-statistics attack (Serwadda and Phoha): keystroke windows from a
  typist whose parameters are the population medians, scored against each user.
- Latency: in-process time per window for feature extraction, scoring and the
  trust update (database and network time are not included).
Bootstrap intervals are over users (2000 resamples, seed 0).
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

from ml.metrics import bootstrap_ci, eer, roc_auc
from ml.profile import score_window, train_template
from ml.synthetic import PRIORS, SyntheticUser, generate_session, load_session
from ml.trust import TrustEngine
from server.features.interaction import InteractionWindower, extract_interaction
from server.features.keystroke import extract_keystroke
from server.features.pointer import PointerWindower, extract_pointer
from server.features.schemas import IF1, IF1_NAMES, KF1, KF1_NAMES, PF1, PF1_NAMES
from server.features.types import KeyPress, PointerSample
from server.features.windowing import KeystrokeWindower
from server.policy.bots import check_window, replay_flag
from server.policy.engine import DEFAULT_POLICY, classify

DATA = Path("data/synthetic")
OUT = Path("experiments/results")
SEED = 0
CHANNELS = {
    "keystroke": (KeystrokeWindower, extract_keystroke, KF1, KF1_NAMES),
    "pointer": (PointerWindower, extract_pointer, PF1, PF1_NAMES),
    "interaction": (InteractionWindower, extract_interaction, IF1, IF1_NAMES),
}


def _end_t(channel, window) -> float:
    if channel == "keystroke":
        return max(p.up_t for p in window)
    if channel == "pointer":
        return max(s.t for stroke in window for s in stroke)
    return max(e.t for e in window)


def _actions(channel, window) -> int:
    return len(window)


def windows_of(events) -> dict[str, list[dict]]:
    out = {}
    for ch, (W, extract, _schema, _names) in CHANNELS.items():
        rows = []
        for w in W().add(events):
            fv = extract(w)
            rows.append({"x": np.array(fv.values), "q": fv.quality, "t": _end_t(ch, w), "n": _actions(ch, w)})
        out[ch] = rows
    return out


def load_cohort():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    users = []
    for u in manifest["users"]:
        sessions = []
        for s in u["sessions"]:
            ev = load_session(DATA / u["user_id"] / s["file"])
            sessions.append({"day": s["day"], "windows": windows_of(ev), "seconds": ev[-1][1] / 1000.0})
        users.append({"id": u["user_id"], "device": u["device"], "sessions": sessions})
    return manifest, users


def enrol(user) -> dict:
    templates = {}
    for ch, (_W, _e, schema, names) in CHANNELS.items():
        rows = [r for s in user["sessions"][:2] for r in s["windows"][ch]]
        if len(rows) >= 5:
            templates[ch] = train_template(ch, schema, names, [r["x"] for r in rows], [r["q"] for r in rows])
    return templates


def _summ(values) -> dict:
    v = np.asarray(values, dtype=float)
    return {"mean": float(v.mean()), "ci95": list(bootstrap_ci(v, seed=SEED)), "n_users": int(v.size)}


def channel_eers(users, rng) -> dict:
    out = {}
    for ch in CHANNELS:
        groups = {"all": users} if ch != "pointer" else {
            "mouse": [u for u in users if u["device"] == "mouse"],
            "touchpad": [u for u in users if u["device"] == "touchpad"]}
        for label, group in groups.items():
            eers, aucs = [], []
            for u in group:
                t = u["templates"].get(ch)
                if t is None:
                    continue
                genuine = [r for s in u["sessions"][2:] for r in s["windows"][ch][::2]]
                pool = [r for o in group if o is not u for s in o["sessions"][2:] for r in s["windows"][ch][::2]]
                if len(genuine) < 3 or not pool:
                    continue
                impostor = [pool[i] for i in rng.choice(len(pool), size=min(len(pool), max(len(genuine), 50)), replace=False)]
                g = [score_window(t, r["x"], 1.0)["score"] for r in genuine]
                im = [score_window(t, r["x"], 1.0)["score"] for r in impostor]
                eers.append(eer(g, im))
                aucs.append(roc_auc(g, im))
            key = ch if label == "all" else f"{ch}_{label}"
            out[key] = {"eer": _summ(eers), "auc": _summ(aucs)}
    return out


def _attempts(session, kt, pt):
    ks, ps = session["windows"]["keystroke"][::2], session["windows"]["pointer"]
    if not ps:
        return []
    out = []
    for k in ks:
        p = min(ps, key=lambda r: abs(r["t"] - k["t"]))
        out.append((score_window(kt, k["x"], 1.0)["score"], score_window(pt, p["x"], 1.0)["score"]))
    return out


def fusion(users, rng) -> dict:
    rows = []
    for u in users:
        kt, pt = u["templates"].get("keystroke"), u["templates"].get("pointer")
        if not (kt and pt):
            continue
        g = [a for s in u["sessions"][2:] for a in _attempts(s, kt, pt)]
        others = [o for o in users if o is not u and o["device"] == u["device"]]
        im = []
        for o in others:
            im += _attempts(o["sessions"][2 + int(rng.integers(0, 4))], kt, pt)[:6]
        if len(g) < 3 or not im:
            continue
        g, im = np.array(g), np.array(im)
        rows.append({name: eer(gs, is_) for name, gs, is_ in (
            ("keystroke", g[:, 0], im[:, 0]), ("pointer", g[:, 1], im[:, 1]),
            ("fused", g.mean(axis=1), im.mean(axis=1)))} |
            {f"{name}_auc": roc_auc(gs, is_) for name, gs, is_ in (
                ("fused", g.mean(axis=1), im.mean(axis=1)),)})
    out = {name: _summ([r[name] for r in rows]) for name in ("keystroke", "pointer", "fused")}
    out["fused_auc"] = _summ([r["fused_auc"] for r in rows])
    for name in ("keystroke", "pointer"):
        out[f"fused_minus_{name}"] = _summ([r["fused"] - r[name] for r in rows])
    return out


def _stream(session, templates):
    """Time-ordered (t, channel, score result, actions) for a session's windows."""
    items = []
    for ch, rows in session["windows"].items():
        t = templates.get(ch)
        if t is None:
            continue
        for r in rows:
            items.append((r["t"], ch, score_window(t, r["x"], r["q"]), r["n"]))
    return sorted(items, key=lambda i: i[0])


def friction(users) -> dict:
    strong_episodes, moderate_episodes, hours = 0, 0, 0.0
    per_user = []
    for u in users:
        u_strong, u_hours = 0, 0.0
        for s in u["sessions"][2:]:
            engine = TrustEngine("s", u["id"], now=0.0)
            prev = None
            for t, ch, res, _n in _stream(s, u["templates"]):
                upd = engine.update(ch, {**res, "window_id": None}, now=t / 1000.0)
                level = classify(upd, DEFAULT_POLICY)
                if level != prev and level == "strong_deviation":
                    strong_episodes += 1
                    u_strong += 1
                if level != prev and level == "moderate_deviation":
                    moderate_episodes += 1
                prev = level
            hours += s["seconds"] / 3600
            u_hours += s["seconds"] / 3600
        per_user.append(u_strong / u_hours)
    return {"genuine_hours": hours, "strong_deviation_episodes": strong_episodes,
            "step_ups_per_hour": strong_episodes / hours, "moderate_episodes_per_hour": moderate_episodes / hours,
            "step_ups_per_hour_per_user": _summ(per_user)}


def time_to_detect(users, rng) -> dict:
    res = {"75": {"seconds": [], "actions": [], "missed": 0}, "50": {"seconds": [], "actions": [], "missed": 0}}
    for u in users:
        others = [o for o in users if o is not u]
        for j in rng.choice(len(others), size=min(10, len(others)), replace=False):
            attacker = others[j]["sessions"][2 + int(rng.integers(0, 4))]
            stream = _stream(attacker, u["templates"])
            if not stream:
                continue
            engine = TrustEngine("i", u["id"], now=0.0)
            t0, actions, hit = stream[0][0], 0, {}
            for t, ch, r, n in stream:
                actions += n
                upd = engine.update(ch, {**r, "window_id": None}, now=t / 1000.0)
                for th in ("75", "50"):
                    if th not in hit and upd["trust"] is not None and upd["trust"] < float(th):
                        hit[th] = ((t - t0) / 1000.0, actions)
                if len(hit) == 2:
                    break
            for th in ("75", "50"):
                if th in hit:
                    res[th]["seconds"].append(hit[th][0])
                    res[th]["actions"].append(hit[th][1])
                else:
                    res[th]["missed"] += 1
    out = {}
    for th, v in res.items():
        total = len(v["seconds"]) + v["missed"]
        out[th] = {"detected_rate": len(v["seconds"]) / total, "takeovers": total,
                   "seconds_median": float(np.median(v["seconds"])) if v["seconds"] else None,
                   "seconds_p90": float(np.percentile(v["seconds"], 90)) if v["seconds"] else None,
                   "actions_median": float(np.median(v["actions"])) if v["actions"] else None}
    return out


def drift(users) -> dict:
    """Keystroke EER per user on test sessions recorded on an enrolment day versus on later days."""
    same, later = [], []
    for u in users:
        u_same, u_later = [], []
        t = u["templates"].get("keystroke")
        enrol_days = {s["day"] for s in u["sessions"][:2]}
        others = [r for o in users if o is not u for s in o["sessions"][2:] for r in s["windows"]["keystroke"][::4]][:200]
        im = [score_window(t, r["x"], 1.0)["score"] for r in others]
        for s in u["sessions"][2:]:
            g = [score_window(t, r["x"], 1.0)["score"] for r in s["windows"]["keystroke"][::2]]
            (u_same if s["day"] in enrol_days else u_later).append(eer(g, im))
        if u_same:
            same.append(float(np.mean(u_same)))
        if u_later:
            later.append(float(np.mean(u_later)))
    return {"keystroke_eer_same_day_as_enrolment": _summ(same) if len(same) > 1 else None,
            "keystroke_eer_later_days": _summ(later)}


def bots(users, rng) -> dict:
    out = {}
    scripted = [extract_keystroke([KeyPress(1 if k % 6 else 3, 150.0 * k + i * 9000, 150.0 * k + 80 + i * 9000)
                                   for k in range(50)]).values for i in range(50)]
    out["scripted_typing_flagged"] = float(np.mean([any(f["severity"] == "high" for f in check_window("keystroke", KF1_NAMES, v)) for v in scripted]))
    lines = []
    for i in range(50):
        strokes = [[PointerSample(1000.0 * s + 16.0 * k, 10.0 * k + i, 5.0 * k, 3, None) for k in range(15)] for s in range(30)]
        lines.append(extract_pointer(strokes).values)
    out["scripted_pointer_flagged"] = float(np.mean([any(f["severity"] == "high" for f in check_window("pointer", PF1_NAMES, v)) for v in lines]))
    exact, jitter, n = 0, 0, 0
    for u in users:
        stored = [r["x"] for s in u["sessions"][:2] for r in s["windows"]["keystroke"]]
        for x in stored[:: max(len(stored) // 5, 1)][:5]:
            n += 1
            exact += replay_flag(list(x), stored) is not None
            jitter += replay_flag(list(x * (1 + rng.normal(0, 0.01, size=x.size))), stored) is not None
    out["exact_replay_flagged"] = exact / n
    out["jittered_replay_flagged"] = jitter / n
    genuine = [r["x"] for u in users for s in u["sessions"] for r in s["windows"]["keystroke"][::4]]
    out["genuine_keystroke_windows_flagged_high"] = float(np.mean([
        any(f["severity"] == "high" for f in check_window("keystroke", KF1_NAMES, list(x))) for x in genuine]))
    return out


def population_attack(users) -> dict:
    medians = SyntheticUser.from_params("population-average", "mouse", [0, 1, 2, 3, 4, 5],
                                        ks={k: v[1] for k, v in PRIORS["keystroke"].items()},
                                        pt={k: v[1] for k, v in PRIORS["pointer"].items()}, seed=99)
    attack = [r["x"] for i in range(3) for r in windows_of(generate_session(medians, i, 99))["keystroke"][::2]]
    pop_eer, zero_eer = [], []
    for u in users:
        t = u["templates"]["keystroke"]
        g = [score_window(t, r["x"], 1.0)["score"] for s in u["sessions"][2:] for r in s["windows"]["keystroke"][::2]]
        z = [score_window(t, r["x"], 1.0)["score"] for o in users if o is not u for r in o["sessions"][3]["windows"]["keystroke"][::8]]
        a = [score_window(t, x, 1.0)["score"] for x in attack]
        pop_eer.append(eer(g, a))
        zero_eer.append(eer(g, z))
    return {"keystroke_eer_vs_population_average_typist": _summ(pop_eer),
            "keystroke_eer_vs_zero_effort_impostors": _summ(zero_eer),
            "attack_windows": len(attack)}


def latency(users) -> dict:
    u = users[0]
    events = load_session(DATA / u["id"] / json.loads((DATA / "manifest.json").read_text())["users"][0]["sessions"][3]["file"])
    times = []
    engine = TrustEngine("l", u["id"], now=0.0)
    for ch, (W, extract, _s, _n) in CHANNELS.items():
        for w in W().add(events):
            start = time.perf_counter()
            fv = extract(w)
            r = score_window(u["templates"][ch], fv.values, fv.quality)
            engine.update(ch, {**r, "window_id": None}, now=0.0)
            times.append((time.perf_counter() - start) * 1000)
    return {"windows": len(times), "ms_p50": float(np.percentile(times, 50)), "ms_p95": float(np.percentile(times, 95))}


def main() -> None:
    rng = np.random.default_rng(SEED)
    manifest, users = load_cohort()
    for u in users:
        u["templates"] = enrol(u)
    results = {
        "experiment": "synthetic_evaluation",
        "synthetic": True,
        "command": "python -m experiments.synthetic_evaluation",
        "cohort": {"users": len(users), "seed": manifest["seed"],
                   "mouse": sum(u["device"] == "mouse" for u in users),
                   "touchpad": sum(u["device"] == "touchpad" for u in users),
                   "sessions": sum(len(u["sessions"]) for u in users),
                   "active_hours": sum(s["seconds"] for u in users for s in u["sessions"]) / 3600},
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform()},
    }
    results["channels"] = channel_eers(users, rng)
    results["fusion"] = fusion(users, rng)
    results["friction"] = friction(users)
    results["time_to_detect"] = time_to_detect(users, rng)
    results["drift"] = drift(users)
    results["bots"] = bots(users, rng)
    results["population_attack"] = population_attack(users)
    results["latency"] = latency(users)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "synthetic_evaluation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in results.items() if k not in ("environment",)}, indent=1)[:6000])


if __name__ == "__main__":
    main()
