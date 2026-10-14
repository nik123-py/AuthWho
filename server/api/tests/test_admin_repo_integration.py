"""Admin queries against PostgreSQL."""

import uuid

import pytest

from server.api.admin_repo import PgAdminRepository
from server.policy.decisions import build_decision
from server.policy.engine import DEFAULT_POLICY
from server.policy.repository import PgPolicyRepository
from server.policy.tests.test_decisions import update
from server.worker.scoring_store import PgScoringStore
from server.worker.tests.test_integration import _user

pytestmark = pytest.mark.integration


def test_sessions_timeline_decisions_and_policy_update(pg_conn, pg_url):
    uid, sid = _user(pg_conn)
    store = PgScoringStore(pg_url, b"k" * 32)
    for seq, trust in ((1, 92.0), (2, 61.0)):
        store.insert_trust_point({**update(trust=trust), "session_id": sid, "user_id": uid, "seq": seq,
                                  "at": "2026-10-14T10:00:0%dZ" % seq})
    ctx = {"session_id": sid, "user_id": uid, "app_id": "demo", "role": "analyst"}
    PgPolicyRepository(pg_url).insert_decision(build_decision(ctx, "trust_update", update(trust=61.0), DEFAULT_POLICY))

    repo = PgAdminRepository(pg_url)
    row = next(r for r in repo.list_sessions(500) if r["session_id"] == sid)
    assert row["trust"] == 61.0 and row["state"] == "scored" and row["level"] == "moderate_deviation"
    assert [p["trust"] for p in repo.timeline(sid)] == [92.0, 61.0]
    assert repo.timeline(sid)[0]["channels"]["keystroke"]["status"] == "scored"
    assert repo.decisions(sid)[0]["explanation"].endswith(".")
    assert repo.session(str(uuid.uuid4())) is None

    pg_conn.execute("INSERT INTO policies (policy_id, app_id, role, high, strong, channel_low, action_sensitivity) "
                    "VALUES ('demo-analyst', 'demo', 'analyst', 75, 50, 0.5, '{\"add_payee\": \"high\"}') "
                    "ON CONFLICT (policy_id) DO NOTHING")
    before = next(p for p in repo.policies() if p["policy_id"] == "demo-analyst")
    after = repo.update_policy("demo-analyst", {**before, "high": 80.0})
    assert after["high"] == 80.0 and after["version"] == before["version"] + 1
    repo.update_policy("demo-analyst", before)
    assert repo.update_policy("missing", before) is None
