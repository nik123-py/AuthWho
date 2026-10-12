"""Decisions table, append-only trigger, retention and policies against PostgreSQL."""

import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from server.db import retention
from server.policy.decisions import build_decision
from server.policy.engine import DEFAULT_POLICY
from server.policy.repository import PgPolicyRepository
from server.policy.tests.test_decisions import update
from server.worker.tests.test_integration import _user

pytestmark = pytest.mark.integration


def _session(pg_conn):
    uid, sid = _user(pg_conn)
    return {"session_id": sid, "user_id": uid, "app_id": "demo", "role": "analyst"}


def test_seeded_policy_and_unknown_role_fallback(pg_url):
    repo = PgPolicyRepository(pg_url)
    policy, exempt = repo.load_policy("demo", "analyst")
    assert (policy.high, policy.strong, policy.channel_low, exempt) == (75.0, 50.0, 0.5, False)
    assert policy.action_sensitivity["add_payee"] == "high"
    assert repo.load_policy("demo", "nobody")[0] == DEFAULT_POLICY


def test_insert_list_and_session_context(pg_conn, pg_url):
    repo = PgPolicyRepository(pg_url)
    s = _session(pg_conn)
    assert repo.session_context(s["session_id"]) == s
    d = build_decision(s, "action_request", update(), DEFAULT_POLICY, action_code="add_payee")
    repo.insert_decision(d)
    rows = repo.list_decisions(s["session_id"])
    assert len(rows) == 1 and rows[0]["decision_id"] == d["decision_id"]
    assert rows[0]["outcome"] == "step_up" and rows[0]["explanation"] == d["explanation"]
    assert rows[0]["window_ids"] == d["window_ids"]


def test_decisions_are_append_only(pg_conn, pg_url):
    repo = PgPolicyRepository(pg_url)
    s = _session(pg_conn)
    d = build_decision(s, "trust_update", update(), DEFAULT_POLICY)
    repo.insert_decision(d)
    with psycopg.connect(pg_url) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("UPDATE decisions SET outcome = 'continue' WHERE decision_id = %s", (d["decision_id"],))
    with psycopg.connect(pg_url) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM decisions WHERE decision_id = %s", (d["decision_id"],))
    assert len(repo.list_decisions(s["session_id"])) == 1


def test_retention_deletes_only_old_decisions(pg_conn, pg_url):
    repo = PgPolicyRepository(pg_url)
    s = _session(pg_conn)
    old = build_decision(s, "trust_update", update(), DEFAULT_POLICY)
    new = build_decision(s, "trust_update", update(), DEFAULT_POLICY)
    repo.insert_decision(old)
    repo.insert_decision(new)
    now = datetime.now(timezone.utc) + timedelta(days=91)
    with psycopg.connect(pg_url) as conn:  # backdate through the retention path's own permission
        conn.execute("ALTER TABLE decisions DISABLE TRIGGER decisions_append_only")
        conn.execute("UPDATE decisions SET created_at = now() + interval '1 day' WHERE decision_id = %s",
                     (new["decision_id"],))
        conn.execute("ALTER TABLE decisions ENABLE TRIGGER decisions_append_only")
    assert retention.run_rule(pg_conn, retention.delete_expired_decisions, now) == 1
    assert [r["decision_id"] for r in repo.list_decisions(s["session_id"])] == [new["decision_id"]]
    assert retention.delete_expired_decisions in retention.DB_RULES
    with pytest.raises(psycopg.errors.RaiseException):
        pg_conn.execute("DELETE FROM decisions WHERE decision_id = %s", (new["decision_id"],))
