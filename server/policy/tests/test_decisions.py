"""Decision records built from trust updates (docs/interfaces.md section 11)."""

import uuid

from server.policy.decisions import build_decision
from server.policy.engine import DEFAULT_POLICY

SESSION = {"session_id": str(uuid.uuid4()), "user_id": str(uuid.uuid4()), "app_id": "demo", "role": "analyst"}


def update(trust=40.0, ks=0.1, pt=0.2):
    def ch(s, wid):
        return {"status": "scored", "score": s, "confidence": 0.9, "fresh": True, "window_id": wid,
                "top_features": [{"name": "flight_median", "z": 3.2}]}
    return {"state": "scored", "trust": trust, "confidence": 0.95,
            "channels": {"keystroke": ch(ks, str(uuid.uuid4())), "pointer": ch(pt, str(uuid.uuid4())),
                         "interaction": {"status": "no_profile", "score": None, "confidence": None, "fresh": False,
                                         "window_id": None, "top_features": []}},
            "bot_flags": [], "model_versions": {"keystroke": "k1", "trust": "trust-pr-1"}}


def test_action_request_on_strong_deviation_asks_for_step_up():
    d = build_decision(SESSION, "action_request", update(), DEFAULT_POLICY, action_code="add_payee")
    assert (d["level"], d["outcome"], d["action_allowed"]) == ("strong_deviation", "step_up", False)
    assert d["action_sensitivity"] == "high"  # looked up from the policy
    assert d["trigger"] == "action_request" and d["action_code"] == "add_payee"
    assert len(d["window_ids"]) == 2 and d["trust"] == 40.0
    assert d["policy_version"] == DEFAULT_POLICY.version
    assert d["explanation"].endswith(".") and "diverged" in d["explanation"]
    assert uuid.UUID(d["decision_id"])


def test_background_update_has_no_action_fields():
    d = build_decision(SESSION, "trust_update", update(trust=90, ks=0.9, pt=0.9), DEFAULT_POLICY)
    assert (d["level"], d["outcome"], d["action_allowed"]) == ("high_confidence", "continue", None)
    assert d["action_code"] is None and d["action_sensitivity"] is None


def test_insufficient_signal_records_null_trust():
    u = {**update(), "state": "insufficient_signal", "trust": None, "confidence": None}
    d = build_decision(SESSION, "action_request", u, DEFAULT_POLICY, action_code="add_payee")
    assert d["level"] == "insufficient_signal" and d["trust"] is None and d["action_allowed"] is True


def test_step_up_results():
    ok = build_decision(SESSION, "step_up_result", update(), DEFAULT_POLICY, step_up_result="passed")
    assert (ok["outcome"], ok["step_up_result"]) == ("continue", "passed")
    assert "passed" in ok["explanation"]
    bad = build_decision(SESSION, "step_up_result", update(), DEFAULT_POLICY, step_up_result="failed")
    assert (bad["level"], bad["outcome"], bad["step_up_result"]) == ("critical", "terminate", "failed")
    assert "identity check failed" in bad["explanation"]


def test_unknown_action_defaults_to_low_sensitivity():
    d = build_decision(SESSION, "action_request", update(trust=60, ks=0.9, pt=0.9), DEFAULT_POLICY, action_code="view_home")
    assert d["action_sensitivity"] == "low" and d["outcome"] == "monitor" and d["action_allowed"] is True
