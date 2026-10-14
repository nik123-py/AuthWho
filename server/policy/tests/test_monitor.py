"""Background policy monitor: one decision per level change, and enforcement."""

import uuid

from server.policy.engine import DEFAULT_POLICY
from server.policy.monitor import PolicyMonitor
from server.policy.tests.test_decisions import update


class FakeRepo:
    def __init__(self, exempt=False):
        self.decisions = []
        self.exempt = exempt
        self.ctx = {}

    def session_context(self, session_id):
        return self.ctx.setdefault(session_id, {"session_id": session_id, "user_id": str(uuid.uuid4()),
                                                "app_id": "demo", "role": "analyst"})

    def load_policy(self, app_id, role):
        return DEFAULT_POLICY, self.exempt

    def insert_decision(self, d):
        self.decisions.append(d)


class FakeControl:
    def __init__(self):
        self.calls = []

    def publish_decision(self, d):
        self.calls.append(("publish", d["outcome"]))

    def require_step_up(self, session_id, decision_id):
        self.calls.append(("step_up", session_id))

    def terminate(self, session_id, decision_id):
        self.calls.append(("terminate", session_id))


def u(sid, **kw):
    return {**update(**kw), "session_id": sid}


def test_one_decision_per_level_change():
    repo, ctl = FakeRepo(), FakeControl()
    m = PolicyMonitor(repo, ctl)
    sid = str(uuid.uuid4())
    assert m.on_update(u(sid, trust=95, ks=0.9, pt=0.9))["level"] == "high_confidence"
    assert m.on_update(u(sid, trust=96, ks=0.8, pt=0.9)) is None  # same level, nothing recorded
    assert m.on_update(u(sid, trust=60, ks=0.9, pt=0.9))["outcome"] == "monitor"
    assert [d["level"] for d in repo.decisions] == ["high_confidence", "moderate_deviation"]
    assert all(d["trigger"] == "trust_update" for d in repo.decisions)
    assert ("step_up", sid) not in ctl.calls


def test_strong_deviation_requires_step_up():
    repo, ctl = FakeRepo(), FakeControl()
    m = PolicyMonitor(repo, ctl)
    sid = str(uuid.uuid4())
    d = m.on_update(u(sid, trust=40, ks=0.05, pt=0.08))
    assert d["outcome"] == "step_up"
    assert ("step_up", sid) in ctl.calls and ("publish", "step_up") in ctl.calls


def test_confirmed_automation_terminates():
    repo, ctl = FakeRepo(), FakeControl()
    m = PolicyMonitor(repo, ctl)
    sid = str(uuid.uuid4())
    bot = {**u(sid, trust=95, ks=0.9, pt=0.9), "bot_flags": [{"kind": "timing_regularity", "severity": "high", "evidence": "x"}]}
    assert m.on_update(bot)["outcome"] == "terminate"
    assert ("terminate", sid) in ctl.calls


def test_exempt_role_records_nothing_and_never_acts():
    repo, ctl = FakeRepo(exempt=True), FakeControl()
    m = PolicyMonitor(repo, ctl)
    assert m.on_update(u(str(uuid.uuid4()), trust=40, ks=0.05, pt=0.08)) is None
    assert repo.decisions == [] and ctl.calls == []
