"""Synthetic volunteer cohort (stand-in for the consented dataset of proposal Section 13).

THIS IS SYNTHETIC DATA. It lets the whole pipeline and the evaluation run end to
end before real volunteers are recorded. Results computed on it describe how
the system behaves on behaviour generated from these models; they are not
measurements of real people and never replace the volunteer study.

Design, mirroring the volunteer protocol (25 people, 6 sessions of about 15
minutes each, over at least 3 days within two weeks, device recorded):
- Each person's parameters are drawn from distributions fitted to real public
  data: keystroke medians and spreads from the Aalto 136M keystrokes subset (500
  typists), pointer kinematics from SapiMouse (120 users). ``PRIORS`` holds the
  10th, 50th and 90th percentiles measured on 2026-10-14; a log-normal is fitted
  through them.
- Typing: English-like words with capitals (Shift held across the letter),
  digits, punctuation, mistakes corrected with backspace bursts, and pauses.
  Key-down to key-down latencies follow the person's median with their own
  multiplier per category pair (their "rhythm signature"); holds follow their
  dwell median per category. Rollover arises when a hold outlasts the gap.
- Pointer: minimum-jerk movements to targets with a person-specific bow
  (curvature), speed, overshoot and pre-click pause, sampled near 60 Hz with
  jitter. Touchpad users move more slowly, split long movements into clutched
  sub-strokes and tap with shorter clicks.
- Interaction: page changes, form field focus order and dwell, scrolling and
  marked sensitive actions.
- Drift: every day has small multiplicative shifts in the person's parameters,
  and typing slows slightly over a session.

Every event uses the SDK format of docs/interfaces.md section 5 (arrays of
numbers only), so the live windowers and extractors process it unchanged.

Usage:
    .venv/Scripts/python -m ml.synthetic --users 25 --seed 2026 --out data/synthetic
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import uuid
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# (p10, median, p90) per parameter, measured from the public datasets.
PRIORS = {
    "keystroke": {
        "dwell_median": (80.0, 105.0, 142.55),
        "dwell_cv": (0.256, 0.330, 0.425),
        "dd_median": (114.9, 168.0, 248.4),
        "dd_cv": (0.546, 0.651, 0.753),
        "backspace_rate": (0.003, 0.045, 0.093),
        "rollover_bias": (0.044, 0.181, 0.439),
        "pause_rate": (0.019, 0.027, 0.083),
    },
    "pointer": {
        "duration": (509.9, 634.0, 783.1),
        "efficiency": (0.807, 0.887, 0.944),
        "curvature": (0.064, 0.098, 0.137),
        "click_hold": (69.85, 86.75, 124.1),
        "pre_click": (27.9, 54.75, 125.3),
        "path_length": (439.9, 607.1, 857.7),
    },
}
Z90 = 1.2816
CATEGORY_PAIRS = [(a, b) for a in range(1, 8) for b in range(1, 8)]
LETTER, DIGIT, SPACE, BACKSPACE, MODIFIER, OTHER = 1, 2, 3, 4, 5, 7


def _draw(rng: np.random.Generator, p10: float, med: float, p90: float) -> float:
    sigma = max((math.log(p90) - math.log(p10)) / (2 * Z90), 1e-3)
    return float(math.exp(rng.normal(math.log(med), sigma)))


@dataclass
class SyntheticUser:
    user_id: str
    device: str
    session_days: list[int]
    ks: dict[str, float]
    pt: dict[str, float]
    rhythm: dict[str, float] = field(default_factory=dict)
    day_drift: dict[int, float] = field(default_factory=dict)

    @classmethod
    def from_params(cls, user_id, device, days, ks, pt, seed=0) -> "SyntheticUser":
        rng = np.random.default_rng(seed)
        rhythm = {f"{a}-{b}": float(np.clip(rng.normal(1.0, 0.15), 0.6, 1.5)) for a, b in CATEGORY_PAIRS}
        drift = {d: float(np.clip(rng.normal(1.0, 0.05), 0.85, 1.15)) for d in set(days)}
        return cls(user_id, device, sorted(days), dict(ks), dict(pt), rhythm, drift)


def make_users(n: int, seed: int, touchpad_share: float = 0.4) -> list[SyntheticUser]:
    rng = np.random.default_rng(seed)
    n_touch = round(n * touchpad_share)
    devices = ["touchpad"] * n_touch + ["mouse"] * (n - n_touch)
    rng.shuffle(devices)
    users = []
    for i in range(n):
        ks = {k: _draw(rng, *v) for k, v in PRIORS["keystroke"].items()}
        pt = {k: _draw(rng, *v) for k, v in PRIORS["pointer"].items()}
        pt["efficiency"] = min(pt["efficiency"], 0.985)
        while True:  # 6 sessions over at least 3 distinct days within two weeks
            days = sorted(int(d) for d in rng.integers(0, 14, size=6))
            if len(set(days)) >= 3:
                break
        uid = str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | int(rng.integers(0, 2**63)), version=4))
        users.append(SyntheticUser.from_params(uid, devices[i], days, ks, pt, seed=int(rng.integers(0, 2**31))))
    return users


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0


def _lognormal(rng, median: float, cv: float) -> float:
    sigma = math.sqrt(math.log(1 + cv * cv))
    return float(median * math.exp(rng.normal(0.0, sigma)))


def _words(rng, n_keys: int):
    """Category sequence for English-like text, with capitals, digits, punctuation and typos."""
    seq, sentence_start = [], True
    while len(seq) < n_keys:
        length = int(np.clip(rng.geometric(1 / 4.7), 1, 12))
        for j in range(length):
            if j == 0 and sentence_start:
                seq.append("cap")
            elif rng.random() < 0.02:
                seq.append(DIGIT)
            else:
                seq.append(LETTER)
            if rng.random() < 0.035:
                seq.append("typo")
        sentence_start = False
        if rng.random() < 0.08:
            seq.append(OTHER)
            sentence_start = True
        seq.append(SPACE)
    return seq[:n_keys]


def _type(events, rng, u: SyntheticUser, clock: _Clock, n_keys: int, drift: float, press_id: list[int], field_index=None):
    ks = u.ks
    prev_cat = SPACE
    for i, tok in enumerate(_words(rng, n_keys)):
        fatigue = 1.0 + 0.10 * (i / max(n_keys, 1))
        keys = []
        if tok == "cap":
            keys = [(MODIFIER, "shift"), (LETTER, None)]
        elif tok == "typo":
            n_bs = 1 + int(rng.random() < 0.3)
            keys = [(LETTER, None)] + [(BACKSPACE, None)] * n_bs + [(LETTER, None)] * n_bs
        elif rng.random() < ks["backspace_rate"] * 0.3:
            keys = [(tok, None), (BACKSPACE, None), (tok, None)]
        else:
            keys = [(tok, None)]
        shift_up = None
        for cat, role in keys:
            gap = _lognormal(rng, 1.08 * ks["dd_median"] * u.rhythm[f"{prev_cat}-{cat}"] * drift * fatigue, ks["dd_cv"] * 0.6)
            if rng.random() < ks["pause_rate"]:
                gap += float(rng.uniform(1000, 4000))
            clock.t += max(gap, 25.0)
            factor = {SPACE: 1.08, BACKSPACE: 0.92, MODIFIER: 1.0}.get(cat, 1.0)
            hold = _lognormal(rng, ks["dwell_median"] * factor * drift, ks["dwell_cv"])
            if rng.random() < ks["rollover_bias"] * 0.1:
                hold = max(hold, gap * 1.1)
            pid = press_id[0]
            press_id[0] += 1
            down = round(clock.t, 1)
            if role == "shift":
                events.append([1, down, MODIFIER, pid])
                shift_up = (pid, down + hold + ks["dd_median"] * 0.8)
            else:
                events.append([1, down, cat, pid])
                events.append([2, round(down + max(hold, 15.0), 1), cat, pid])
                if shift_up:
                    events.append([2, round(max(shift_up[1], down + 20.0), 1), MODIFIER, shift_up[0]])
                    shift_up = None
            prev_cat = cat


def _move(events, rng, u: SyntheticUser, clock: _Clock, pos: list[float], drift: float, click: bool):
    pt = u.pt
    touch = u.device == "touchpad"
    dist = _lognormal(rng, pt["path_length"] * 0.95, 0.45)
    angle = rng.uniform(0, 2 * math.pi)
    target = [min(max(pos[0] + dist * math.cos(angle), 5), 1900), min(max(pos[1] + dist * math.sin(angle), 5), 1050)]
    parts = 1 + (int(rng.integers(1, 3)) if touch and dist > 350 else 0)
    start = list(pos)
    bow = pt["curvature"] * 3.0 * (1 if rng.random() < 0.5 else -1)
    for part in range(parts):
        a, b = part / parts, (part + 1) / parts
        p0 = [start[0] + (target[0] - start[0]) * a, start[1] + (target[1] - start[1]) * a]
        p1 = [start[0] + (target[0] - start[0]) * b, start[1] + (target[1] - start[1]) * b]
        seg = math.dist(p0, p1)
        dur = _lognormal(rng, 0.85 * pt["duration"] * (seg / pt["path_length"]) ** 0.6 * drift * (1.35 if touch else 1.0), 0.18)
        steps = max(int(dur / 16.7), 6)
        nx, ny = -(p1[1] - p0[1]) / max(seg, 1e-6), (p1[0] - p0[0]) / max(seg, 1e-6)
        for k in range(1, steps + 1):
            tau = k / steps
            s = 10 * tau**3 - 15 * tau**4 + 6 * tau**5
            off = bow * seg * math.sin(math.pi * s)
            x = p0[0] + (p1[0] - p0[0]) * s + nx * off + rng.normal(0, 0.5)
            y = p0[1] + (p1[1] - p0[1]) * s + ny * off + rng.normal(0, 0.5)
            clock.t += max(dur / steps + rng.normal(0, 1.5), 4.0)
            events.append([3, round(clock.t, 1), int(round(x)), int(round(y))])
        if part < parts - 1:
            clock.t += float(rng.uniform(320, 600))  # touchpad clutch: finger lifted and placed again
    pos[:] = target
    if click:
        clock.t += _lognormal(rng, pt["pre_click"], 0.5)
        hold = _lognormal(rng, pt["click_hold"] * (0.7 if touch else 1.0), 0.25)
        x, y = int(round(pos[0])), int(round(pos[1]))
        events.append([4, round(clock.t, 1), x, y, 0])
        clock.t += hold
        events.append([5, round(clock.t, 1), x, y, 0])
    clock.t += float(rng.uniform(350, 1400))


def generate_session(u: SyntheticUser, session_index: int, seed: int) -> list[list[float]]:
    """One roughly 15-minute session: free-text writing, form filling and browsing."""
    rng = np.random.default_rng([seed, session_index, zlib.crc32(u.user_id.encode())])
    drift = u.day_drift[u.session_days[session_index]]
    clock, events, press_id, pos = _Clock(), [], [0], [960.0, 540.0]

    events.append([12, 0.0, 1])
    for _ in range(int(rng.integers(8, 14))):  # navigate to the writing task
        _move(events, rng, u, clock, pos, drift, click=rng.random() < 0.8)
    events.append([12, round(clock.t, 1), 2])
    events.append([8, round(clock.t, 1), 0, 5])
    _type(events, rng, u, clock, int(rng.integers(700, 950)), drift, press_id)
    events.append([9, round(clock.t, 1), 0])

    events.append([12, round(clock.t + 500, 1), 3])  # form filling
    clock.t += 500
    order = list(range(6))
    if rng.random() < 0.3:
        i = int(rng.integers(0, 5))
        order[i], order[i + 1] = order[i + 1], order[i]
    for idx in order:
        _move(events, rng, u, clock, pos, drift, click=True)
        events.append([8, round(clock.t, 1), idx, 1])
        _type(events, rng, u, clock, int(rng.integers(12, 30)), drift, press_id)
        events.append([9, round(clock.t, 1), idx])

    events.append([12, round(clock.t + 400, 1), 5])  # browsing reports and payees
    clock.t += 400
    for k in range(int(rng.integers(120, 160))):
        if rng.random() < 0.35:
            for _ in range(int(rng.integers(2, 6))):
                clock.t += float(rng.uniform(60, 180))
                events.append([6, round(clock.t, 1), 0.0, float(rng.choice([100.0, -100.0], p=[0.8, 0.2])), 0])
        _move(events, rng, u, clock, pos, drift, click=rng.random() < 0.8)
        if k % 25 == 24:
            events.append([13, round(clock.t, 1), 1])
    events.sort(key=lambda e: e[1])
    return events


def generate_cohort(out: Path, n_users: int = 25, seed: int = 2026) -> dict:
    out = Path(out)
    users = make_users(n_users, seed)
    manifest = {"synthetic": True, "seed": seed, "n_users": n_users, "priors": PRIORS, "users": []}
    for u in users:
        folder = out / u.user_id
        folder.mkdir(parents=True, exist_ok=True)
        sessions = []
        for i, day in enumerate(u.session_days):
            events = generate_session(u, i, seed)
            name = f"session{i + 1}_day{day:02d}.json.gz"
            with gzip.open(folder / name, "wt", encoding="utf-8") as fh:
                json.dump(events, fh)
            sessions.append({"file": name, "day": day, "events": len(events)})
        manifest["users"].append({"user_id": u.user_id, "device": u.device, "sessions": sessions,
                                  "keystroke": u.ks, "pointer": u.pt})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_session(path: Path) -> list[list[float]]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the synthetic volunteer cohort.")
    ap.add_argument("--users", type=int, default=25)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default="data/synthetic")
    args = ap.parse_args()
    m = generate_cohort(Path(args.out), args.users, args.seed)
    n = sum(len(u["sessions"]) for u in m["users"])
    print(f"wrote {len(m['users'])} synthetic users, {n} sessions to {args.out}")


if __name__ == "__main__":
    main()
