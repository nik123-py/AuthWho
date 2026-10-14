"""Policy engine: trust levels, outcomes and explanations (docs/interfaces.md section 11)."""

import pytest

from server.policy.engine import DEFAULT_POLICY, classify, decide, explain, explain_for_user


def update(trust=90.0, ks=0.8, pt=0.8, it=None, state="scored", flags=(), ks_top=None, pt_top=None):
    def ch(score, top):
        if score is None:
            return {"status": "no_profile", "score": None, "confidence": None, "fresh": False, "top_features": []}
        return {"status": "scored", "score": score, "confidence": 0.9, "fresh": True, "top_features": top or []}
    return {
        "state": state,
        "trust": trust if state == "scored" else None,
        "confidence": 0.9 if state == "scored" else None,
        "channels": {"keystroke": ch(ks, ks_top), "pointer": ch(pt, pt_top), "interaction": ch(it, None)},
        "bot_flags": list(flags),
    }


def test_insufficient_signal():
    assert classify(update(state="insufficient_signal"), DEFAULT_POLICY) == "insufficient_signal"
    assert classify(None, DEFAULT_POLICY) == "insufficient_signal"


def test_high_confidence():
    assert classify(update(trust=90), DEFAULT_POLICY) == "high_confidence"


def test_moderate_by_trust_band_or_one_low_channel():
    assert classify(update(trust=60), DEFAULT_POLICY) == "moderate_deviation"
    assert classify(update(trust=90, ks=0.05), DEFAULT_POLICY) == "moderate_deviation"
    # one channel only, very low trust: still a single channel diverging
    assert classify(update(trust=30, ks=0.05, pt=None), DEFAULT_POLICY) == "moderate_deviation"


def test_strong_when_several_channels_diverge_or_replay():
    assert classify(update(trust=40, ks=0.05, pt=0.08), DEFAULT_POLICY) == "strong_deviation"
    replay = {"kind": "replay_match", "severity": "high", "evidence": "x"}
    assert classify(update(trust=95, flags=[replay]), DEFAULT_POLICY) == "strong_deviation"
    weak = {"kind": "replay_match", "severity": "low", "evidence": "x"}
    assert classify(update(trust=95, flags=[weak]), DEFAULT_POLICY) == "high_confidence"


def test_critical_on_confirmed_automation_or_failed_step_up():
    bot = {"kind": "timing_regularity", "severity": "high", "evidence": "x"}
    assert classify(update(trust=95, flags=[bot]), DEFAULT_POLICY) == "critical"
    assert classify(update(trust=40, ks=0.05, pt=0.08), DEFAULT_POLICY, step_up_failed=True) == "critical"
    assert classify(update(trust=90), DEFAULT_POLICY, step_up_failed=True) == "critical"


@pytest.mark.parametrize(
    ("level", "sensitivity", "outcome", "allowed"),
    [
        ("insufficient_signal", None, "continue", True),
        ("insufficient_signal", "high", "continue", True),
        ("high_confidence", "high", "continue", True),
        ("moderate_deviation", None, "monitor", True),
        ("moderate_deviation", "low", "monitor", True),
        ("moderate_deviation", "high", "step_up", False),
        ("strong_deviation", None, "step_up", False),
        ("strong_deviation", "low", "step_up", False),
        ("critical", None, "terminate", False),
        ("critical", "high", "terminate", False),
    ],
)
def test_outcomes(level, sensitivity, outcome, allowed):
    assert decide(level, sensitivity) == (outcome, allowed)


def test_explanations_are_one_plain_sentence():
    top_k = [{"name": "flight_median", "z": 4.1}]
    top_p = [{"name": "velocity_mean", "z": -3.0}]
    cases = {
        "insufficient_signal": update(state="insufficient_signal"),
        "high_confidence": update(),
        "moderate_deviation": update(trust=90, ks=0.05, ks_top=top_k),
        "strong_deviation": update(trust=40, ks=0.05, pt=0.08, ks_top=top_k, pt_top=top_p),
        "critical": update(trust=95, flags=[{"kind": "timing_regularity", "severity": "high", "evidence": "x"}]),
    }
    texts = {level: explain(level, u) for level, u in cases.items()}
    for text in texts.values():
        assert text.endswith(".") and text.count(".") == 1 and "—" not in text
        assert "_" not in text  # no raw feature names
    assert "gap between keys" in texts["moderate_deviation"]
    assert "typing rhythm" in texts["strong_deviation"].lower() and "pointer speed" in texts["strong_deviation"]
    assert "automated" in texts["critical"]
    assert "not enough" in texts["insufficient_signal"].lower()


def test_failed_step_up_explanation_and_user_text_reveal_no_scores():
    text = explain("critical", update(trust=40, ks=0.05, pt=0.08), step_up_failed=True)
    assert "identity check failed" in text
    for outcome in ("continue", "monitor", "step_up", "terminate"):
        msg = explain_for_user(outcome)
        assert msg and not any(ch.isdigit() for ch in msg)
        assert "trust" not in msg.lower() and "score" not in msg.lower()
