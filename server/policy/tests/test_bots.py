"""Bot and replay heuristics (docs/interfaces.md section 10)."""

import numpy as np

from server.features.keystroke import extract_keystroke
from server.features.pointer import extract_pointer
from server.features.schemas import KF1_NAMES, PF1_NAMES
from server.features.types import KeyPress, PointerSample
from server.policy.bots import check_window, replay_flag


def ks_vector(jitter):
    rng = np.random.default_rng(1)
    presses, t = [], 0.0
    for k in range(50):
        hold = 80 + jitter * rng.normal()
        presses.append(KeyPress(1 if k % 6 else 3, t, t + max(hold, 5)))
        t += 150 + jitter * rng.normal()
    return extract_keystroke(presses).values


def stroke(t0, speed, wobble):
    rng = np.random.default_rng(int(t0))
    return [PointerSample(t0 + 10 * i, speed * 10 * i, wobble * rng.normal(), 3, None) for i in range(12)]


def test_human_like_typing_is_not_flagged():
    assert check_window("keystroke", KF1_NAMES, ks_vector(jitter=20.0)) == []


def test_scripted_typing_is_flagged_as_automation():
    flags = check_window("keystroke", KF1_NAMES, ks_vector(jitter=0.0))
    assert flags and flags[0]["kind"] == "timing_regularity" and flags[0]["severity"] == "high"
    assert "ms" in flags[0]["evidence"]


def test_human_like_pointer_is_not_flagged():
    v = extract_pointer([stroke(1000 * i, 0.8, 3.0) for i in range(30)]).values
    assert check_window("pointer", PF1_NAMES, v) == []


def test_perfectly_straight_constant_speed_pointer_is_flagged():
    v = extract_pointer([stroke(1000 * i, 0.8, 0.0) for i in range(30)]).values
    flags = check_window("pointer", PF1_NAMES, v)
    assert flags and flags[0]["kind"] == "implausible_motion" and flags[0]["severity"] == "high"


def test_teleporting_pointer_is_flagged():
    v = extract_pointer([stroke(1000 * i, 60.0, 3.0) for i in range(30)]).values
    flag = check_window("pointer", PF1_NAMES, v)[0]
    assert flag["kind"] == "implausible_motion" and flag["severity"] == "medium"


def test_replay_of_a_stored_window_is_flagged_and_near_misses_are_not():
    stored = [ks_vector(20.0), list(np.array(ks_vector(20.0)) * 1.3)]
    flag = replay_flag(list(stored[0]), stored)
    assert flag["kind"] == "replay_match" and flag["severity"] == "high"
    assert replay_flag(list(np.array(stored[0]) * 1.01), stored) is None
    assert replay_flag(list(stored[0]), []) is None


def test_fast_and_perfectly_straight_is_still_high():
    v = extract_pointer([stroke(1000 * i, 60.0, 0.0) for i in range(30)]).values
    assert check_window("pointer", PF1_NAMES, v)[0]["severity"] == "high"
