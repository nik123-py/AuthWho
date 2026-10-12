"""D11: TOTP enrollment, policy checks on high-risk actions, step-up and session end (P4)."""

import pyotp

from demo_app.backend.tests.conftest import PASSWORD


def _session(client):
    return client.post("/api/authwho/stream").json()["session_id"]


def _totp(client):
    setup = client.post("/api/totp/setup")
    assert setup.status_code == 200 and setup.headers["cache-control"] == "no-store"
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")
    assert client.post("/api/totp/confirm", json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    return secret


def test_totp_setup_needs_a_valid_code_and_secret_is_encrypted(consented, db_path):
    secret = consented.post("/api/totp/setup").json()["secret"]
    assert consented.post("/api/totp/confirm", json={"code": "000000"}).json() == {"error": "invalid_code"}
    assert consented.get("/api/me").json()["totp_enabled"] is False
    assert consented.post("/api/totp/confirm", json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    assert consented.get("/api/me").json()["totp_enabled"] is True
    assert secret.encode() not in db_path.read_bytes()
    assert consented.post("/api/totp/setup").json() == {"error": "totp_already_enabled"}


def test_high_risk_action_allowed_when_policy_allows(consented, collector):
    _session(consented)
    assert consented.post("/api/payees", json={"name": "A", "account": "123"}).json() == {"ok": True}
    call = collector.calls("POST", r"/v1/sessions/.+/actions")[-1]
    assert call.body == {"action_code": "add_payee", "sensitivity": "high"}


def test_step_up_with_totp_then_retry_succeeds(consented, collector):
    secret = _totp(consented)
    _session(consented)
    collector.action_outcome = "step_up"
    r = consented.post("/api/reports/export")
    assert r.status_code == 403 and r.json() == {"error": "step_up_required", "method": "totp"}
    assert consented.get("/api/session").json() == {"status": "step_up_required", "method": "totp"}
    collector.action_outcome = "continue"
    ok = consented.post("/api/step-up", json={"code": pyotp.TOTP(secret).now()})
    assert ok.status_code == 200 and ok.json() == {"status": "active"}
    assert collector.step_up_results == [True]
    assert consented.post("/api/reports/export").json() == {"ok": True}


def test_password_is_the_step_up_without_totp(consented, collector):
    _session(consented)
    collector.action_outcome = "step_up"
    assert consented.post("/api/payees", json={"name": "A", "account": "1"}).json()["method"] == "password"
    assert consented.post("/api/step-up", json={"password": PASSWORD}).json() == {"status": "active"}


def test_three_wrong_answers_end_the_session(consented, collector):
    _session(consented)
    collector.action_outcome = "step_up"
    consented.post("/api/payees", json={"name": "A", "account": "1"})
    for attempt in range(2):
        r = consented.post("/api/step-up", json={"password": "wrong password!"})
        assert r.status_code == 400 and r.json() == {"error": "step_up_failed", "attempts_left": 2 - attempt}
    assert collector.step_up_results == []  # a typo is not yet a failed check
    r = consented.post("/api/step-up", json={"password": "wrong password!"})
    assert r.status_code == 401 and r.json() == {"error": "session_ended"}
    assert collector.step_up_results == [False]
    assert consented.get("/api/me").status_code == 401  # logged out


def test_ended_session_logs_the_user_out_on_the_next_request(consented, collector):
    sid = _session(consented)
    collector.session_status[sid] = "terminated"
    r = consented.get("/api/me")
    assert r.status_code == 401 and r.json() == {"error": "session_ended"}
    assert consented.get("/api/me").json() == {"error": "not_logged_in"}


def test_pending_step_up_blocks_actions_and_notes(consented, collector):
    sid = _session(consented)
    collector.session_status[sid] = "step_up_required"
    assert consented.post("/api/notes", json={"text": "x"}).json() == {"error": "step_up_required", "method": "password"}
    assert consented.get("/api/me").status_code == 200  # the page can still load and show the prompt


def test_authwho_down_falls_back_to_normal_session_rules(consented, collector):
    _session(consented)
    collector.unreachable = True
    assert consented.post("/api/payees", json={"name": "A", "account": "1"}).json() == {"ok": True}


def test_without_capture_actions_follow_normal_rules(logged_in, collector):
    assert logged_in.post("/api/payees", json={"name": "A", "account": "1"}).json() == {"ok": True}
    assert collector.requests == []


def test_step_up_endpoint_requires_a_pending_step_up(consented):
    _session(consented)
    assert consented.post("/api/step-up", json={"password": PASSWORD}).json() == {"error": "no_step_up_pending"}
