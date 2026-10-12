import json

import numpy as np
import pytest

from ml.trust import FRESH_S, TrustEngine


def scored(score, confidence=1.0, window_id="w", top=None):
    return {"status": "scored", "score": score, "confidence": confidence, "window_id": window_id,
            "model_kind": "scaled_manhattan", "model_version": "keystroke-scaled_manhattan-1",
            "top_features": top or []}


def test_new_session_is_insufficient_signal_with_null_trust():
    e = TrustEngine("s", "u", now=0.0)
    u = e.snapshot(now=0.0)
    assert u["state"] == "insufficient_signal"
    assert u["trust"] is None and u["confidence"] is None
    assert set(u["channels"]) == {"keystroke", "pointer", "interaction"}
    assert all(c["status"] == "no_profile" and c["fresh"] is False for c in u["channels"].values())


def test_genuine_like_scores_keep_trust_high():
    rng = np.random.default_rng(0)
    e = TrustEngine("s", "u", now=0.0)
    trusts = []
    for i in range(300):
        ch = "keystroke" if i % 2 else "pointer"
        trusts.append(e.update(ch, scored(float(rng.uniform())), now=float(i))["trust"])
    assert np.mean(trusts) > 75
    assert min(trusts) > 50


def test_impostor_scores_drive_trust_below_50_within_six_windows():
    e = TrustEngine("s", "u", now=0.0)
    for i in range(6):
        u = e.update("keystroke", scored(0.02), now=float(i))
    assert u["trust"] < 50
    assert u["state"] == "scored"


def test_one_odd_window_does_not_collapse_trust():
    e = TrustEngine("s", "u", now=0.0)
    u = e.update("keystroke", scored(0.0), now=1.0)
    assert u["trust"] >= 85


def test_low_confidence_moves_trust_less():
    a = TrustEngine("s", "u", now=0.0).update("keystroke", scored(0.0, confidence=1.0), now=1.0)
    b = TrustEngine("s", "u", now=0.0).update("keystroke", scored(0.0, confidence=0.5), now=1.0)
    assert 100 - b["trust"] == pytest.approx((100 - a["trust"]) / 2)


def test_interaction_channel_counts_half():
    a = TrustEngine("s", "u", now=0.0).update("keystroke", scored(0.0), now=1.0)
    b = TrustEngine("s", "u", now=0.0).update("interaction", scored(0.0), now=1.0)
    assert 100 - b["trust"] == pytest.approx((100 - a["trust"]) / 2)


def test_stale_evidence_becomes_insufficient_signal_and_trust_resumes_later():
    e = TrustEngine("s", "u", now=0.0)
    for i in range(3):
        e.update("keystroke", scored(0.02), now=float(i))
    held = e.trust
    stale = e.snapshot(now=2.0 + FRESH_S + 1)
    assert stale["state"] == "insufficient_signal" and stale["trust"] is None
    assert stale["channels"]["keystroke"]["fresh"] is False
    back = e.update("pointer", scored(0.9), now=2.0 + FRESH_S + 5)
    assert back["state"] == "scored"
    assert back["trust"] > held  # resumed from the retained value, not reset to 100


def test_non_scored_statuses_do_not_move_trust():
    e = TrustEngine("s", "u", now=0.0)
    e.set_status("pointer", "opted_out")
    u = e.update("keystroke", {"status": "low_quality", "score": None, "confidence": None, "window_id": "w",
                               "model_kind": "scaled_manhattan", "model_version": "v", "top_features": []}, now=1.0)
    assert u["state"] == "insufficient_signal"
    assert u["channels"]["pointer"]["status"] == "opted_out"
    assert u["channels"]["keystroke"]["status"] == "low_quality"
    assert e.trust == 100.0


def test_confidence_combines_fresh_channels():
    e = TrustEngine("s", "u", now=0.0)
    e.update("keystroke", scored(0.5, confidence=0.6), now=1.0)
    u = e.update("pointer", scored(0.5, confidence=0.5), now=2.0)
    assert u["confidence"] == pytest.approx(1 - (1 - 0.6) * (1 - 0.5))


def test_message_shape_seq_and_round_trip():
    e = TrustEngine("s1", "u1", now=0.0)
    u1 = e.update("pointer", {**scored(0.7, top=[{"name": "velocity_mean", "z": 1.2}]), "pointer_device": "touchpad"}, now=1.0)
    u2 = e.update("keystroke", scored(0.6), now=2.0)
    assert (u1["v"], u1["session_id"], u1["user_id"]) == (1, "s1", "u1")
    assert u2["seq"] == u1["seq"] + 1
    assert u1["channels"]["pointer"]["pointer_device"] == "touchpad"
    assert u1["channels"]["pointer"]["top_features"][0]["name"] == "velocity_mean"
    assert u2["model_versions"]["keystroke"] == "keystroke-scaled_manhattan-1"
    assert u2["model_versions"]["trust"] == "trust-pr-1"
    assert isinstance(u2["at"], str) and u2["bot_flags"] == []
    restored = TrustEngine.from_dict(json.loads(json.dumps(e.to_dict())))
    assert restored.snapshot(now=3.0) == {**e.snapshot(now=3.0)}
