import json

import numpy as np
import pytest

from ml.profile import TEMPLATE_FORMAT, score_window, train_template

NAMES = [f"f{i}" for i in range(6)]


def _genuine(n, seed=0):
    rng = np.random.default_rng(seed)
    return rng.normal(loc=[10, 20, 30, 40, 50, 60], scale=[1, 2, 3, 4, 5, 6], size=(n, 6))


def test_template_is_json_and_round_trips():
    t = train_template("keystroke", "kf-1", NAMES, _genuine(30), quality=[1.0] * 30)
    restored = json.loads(json.dumps(t))
    assert restored == t
    assert t["format"] == TEMPLATE_FORMAT
    assert t["channel"] == "keystroke" and t["schema"] == "kf-1" and t["n_windows"] == 30
    assert t["model"]["model_kind"] == "scaled_manhattan"
    assert len(t["calibration"]) == 30
    x = _genuine(1, seed=5)[0]
    assert score_window(t, x, quality=1.0) == score_window(restored, x, quality=1.0)


def test_genuine_scores_spread_and_impostor_scores_near_zero():
    t = train_template("keystroke", "kf-1", NAMES, _genuine(40), quality=[1.0] * 40)
    genuine = [score_window(t, x, quality=1.0)["score"] for x in _genuine(200, seed=1)]
    impostor_x = _genuine(200, seed=2) + np.array([4, 8, 12, 16, 20, 24])  # shifted by 4 sd
    impostor = [score_window(t, x, quality=1.0)["score"] for x in impostor_x]
    assert 0.35 < np.mean(genuine) < 0.65  # calibrated: roughly uniform for genuine windows
    assert np.mean(impostor) < 0.05
    assert all(0.0 < s < 1.0 for s in genuine + impostor)


def test_score_result_matches_the_channel_score_contract():
    t = train_template("pointer", "pf-1", NAMES, _genuine(25), quality=[1.0] * 25)
    x = _genuine(1, seed=3)[0].copy()
    x[4] += 50.0  # feature f4 far off
    r = score_window(t, x, quality=0.8)
    assert r["status"] == "scored"
    assert r["model_kind"] == "scaled_manhattan"
    assert r["model_version"] == t["model_version"]
    assert r["confidence"] == pytest.approx(0.8)
    assert r["top_features"][0]["name"] == "f4"
    assert r["top_features"][0]["z"] > 5
    assert len(r["top_features"]) == 3


def test_low_quality_window_is_reported_not_scored():
    t = train_template("keystroke", "kf-1", NAMES, _genuine(25), quality=[1.0] * 25)
    r = score_window(t, _genuine(1)[0], quality=0.2)
    assert r["status"] == "low_quality" and r["score"] is None and r["confidence"] is None


def test_training_rejects_too_few_windows_and_wrong_width():
    with pytest.raises(ValueError):
        train_template("keystroke", "kf-1", NAMES, _genuine(4), quality=[1.0] * 4)
    t = train_template("keystroke", "kf-1", NAMES, _genuine(25), quality=[1.0] * 25)
    with pytest.raises(ValueError):
        score_window(t, np.zeros(5), quality=1.0)


def test_scores_keep_falling_below_the_calibration_floor():
    t = train_template("keystroke", "kf-1", NAMES, _genuine(5), quality=[1.0] * 5)
    floor = 0.5 / (len(t["calibration"]) + 1)
    base = _genuine(1, seed=9)[0]
    near = score_window(t, base + np.array([3, 6, 9, 12, 15, 18]), quality=1.0)["score"]
    far = score_window(t, base + np.array([30, 60, 90, 120, 150, 180]), quality=1.0)["score"]
    assert far < near <= floor
    assert far < floor / 10
    assert far > 0.0
