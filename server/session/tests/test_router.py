"""Session control API (docs/interfaces.md section 11)."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from server.api.app import create_app
from server.common.config import Settings
from server.policy.engine import DEFAULT_POLICY
from server.policy.tests.test_decisions import update

KEY = "test-app-key"
H = {"X-AuthWho-App-Key": KEY}


class FakeControl:
    def __init__(self):
        self.state = {}

    def status(self, sid):
        return self.state.get(sid, {}).get("status")

    def last_decision_id(self, sid):
        return self.state.get(sid, {}).get("last_decision_id")

    def last_trust(self, sid):
        return self.state.get(sid, {}).get("last_trust")

    def verified_at(self, sid):
        return self.state.get(sid, {}).get("verified_at")

    def publish_decision(self, d):
        self.state.setdefault(d["session_id"], {})["last_decision_id"] = d["decision_id"]

    def require_step_up(self, sid, did):
        if self.status(sid) == "active":
            self.state[sid]["status"] = "step_up_required"

    def mark_verified(self, sid, did, now=None):
        self.state[sid].update(status="active", verified_at=time.time())

    def terminate(self, sid, did):
        self.state[sid]["status"] = "terminated"


class FakeRepo:
    def __init__(self):
        self.decisions = []
        self.sessions = {}
        self.exempt = False

    def session_context(self, sid):
        return self.sessions.get(sid)

    def load_policy(self, app_id, role):
        return DEFAULT_POLICY, self.exempt

    def insert_decision(self, d):
        self.decisions.append(d)

    def list_decisions(self, sid):
        return [d for d in self.decisions if d["session_id"] == sid]


@pytest.fixture
def env():
    settings = Settings(app_api_key=KEY, cors_origins=("http://localhost:5173",))
    control, repo = FakeControl(), FakeRepo()
    app = create_app(settings, hot_store=object(), repository=object(), session_control=control, policy_repo=repo)
    sid = str(uuid.uuid4())
    repo.sessions[sid] = {"session_id": sid, "user_id": str(uuid.uuid4()), "app_id": "demo", "role": "analyst"}
    control.state[sid] = {"status": "active"}
    with TestClient(app) as client:
        yield client, control, repo, sid


def trust(control, sid, **kw):
    control.state[sid]["last_trust"] = {**update(**kw), "session_id": sid, "at": "2026-10-12T12:00:00Z"}


def test_requires_app_key_and_known_session(env):
    client, control, repo, sid = env
    assert client.get(f"/v1/sessions/{sid}/status").status_code == 401
    assert client.get(f"/v1/sessions/{uuid.uuid4()}/status", headers=H).json() == {"error": "unknown_session"}


def test_status(env):
    client, control, repo, sid = env
    assert client.get(f"/v1/sessions/{sid}/status", headers=H).json() == {"status": "active", "decision_id": None}


def test_high_risk_action_with_good_trust_is_allowed(env):
    client, control, repo, sid = env
    trust(control, sid, trust=95, ks=0.9, pt=0.9)
    r = client.post(f"/v1/sessions/{sid}/actions", json={"action_code": "add_payee", "sensitivity": "high"}, headers=H).json()
    assert (r["outcome"], r["action_allowed"]) == ("continue", True)
    assert r["explanation_for_user"] == "You can continue."
    assert repo.decisions[-1]["trigger"] == "action_request"


def test_moderate_deviation_requires_step_up_for_high_risk_only(env):
    client, control, repo, sid = env
    trust(control, sid, trust=60, ks=0.9, pt=0.9)
    low = client.post(f"/v1/sessions/{sid}/actions", json={"action_code": "view_report", "sensitivity": "low"}, headers=H).json()
    assert (low["outcome"], low["action_allowed"]) == ("monitor", True)
    high = client.post(f"/v1/sessions/{sid}/actions", json={"action_code": "add_payee", "sensitivity": "high"}, headers=H).json()
    assert (high["outcome"], high["action_allowed"]) == ("step_up", False)
    assert control.status(sid) == "step_up_required"
    assert "trust" not in high["explanation_for_user"].lower()


def test_pending_step_up_blocks_every_action_until_passed(env):
    client, control, repo, sid = env
    trust(control, sid, trust=40, ks=0.1, pt=0.2)
    client.post(f"/v1/sessions/{sid}/actions", json={"action_code": "add_payee"}, headers=H)
    trust(control, sid, trust=95, ks=0.9, pt=0.9)
    r = client.post(f"/v1/sessions/{sid}/actions", json={"action_code": "view_report"}, headers=H).json()
    assert (r["outcome"], r["action_allowed"]) == ("step_up", False)
    ok = client.post(f"/v1/sessions/{sid}/step-up-result", json={"passed": True}, headers=H).json()
    assert (ok["outcome"], ok["status"]) == ("continue", "active")
    trust(control, sid, trust=40, ks=0.1, pt=0.2)  # old evidence from before the check
    control.state[sid]["last_trust"]["at"] = "2000-01-01T00:00:00Z"
    after = client.post(f"/v1/sessions/{sid}/actions", json={"action_code": "add_payee"}, headers=H).json()
    assert after["action_allowed"] is True


def test_failed_step_up_ends_the_session(env):
    client, control, repo, sid = env
    trust(control, sid, trust=40, ks=0.1, pt=0.2)
    r = client.post(f"/v1/sessions/{sid}/step-up-result", json={"passed": False}, headers=H).json()
    assert (r["outcome"], r["status"]) == ("terminate", "terminated")
    assert repo.decisions[-1]["level"] == "critical" and repo.decisions[-1]["step_up_result"] == "failed"
    blocked = client.post(f"/v1/sessions/{sid}/actions", json={"action_code": "add_payee"}, headers=H)
    assert blocked.status_code == 409 and blocked.json() == {"error": "session_ended"}


def test_insufficient_signal_falls_back_to_normal_rules(env):
    client, control, repo, sid = env
    r = client.post(f"/v1/sessions/{sid}/actions", json={"action_code": "add_payee"}, headers=H).json()
    assert (r["outcome"], r["action_allowed"]) == ("continue", True)
    assert repo.decisions[-1]["level"] == "insufficient_signal"


def test_exempt_role_is_never_challenged(env):
    client, control, repo, sid = env
    repo.exempt = True
    trust(control, sid, trust=10, ks=0.01, pt=0.01)
    r = client.post(f"/v1/sessions/{sid}/actions", json={"action_code": "add_payee"}, headers=H).json()
    assert (r["outcome"], r["action_allowed"]) == ("continue", True)
