"""D3: consent is stored locally and forwarded to the AuthWho collector."""

import sqlite3
from datetime import datetime, timedelta, timezone

from .conftest import APP_KEY, CONSENT_BODY, PASSWORD, login

USER_PATH = r"/v1/users/[0-9a-f-]{36}"


def _authwho_user_id(db_path) -> str:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT authwho_user_id FROM users WHERE username = 'alice'").fetchone()[0]


def test_consent_forwards_put_with_mapped_opt_outs(logged_in, collector, db_path):
    response = logged_in.post("/api/consent", json=CONSENT_BODY)
    assert response.status_code == 200

    puts = collector.calls("PUT", USER_PATH)
    assert len(puts) == 1
    put = puts[0]
    assert put.path == f"/v1/users/{_authwho_user_id(db_path)}"
    assert put.headers["X-AuthWho-App-Key"] == APP_KEY
    consent_at = put.body.pop("consent_at")
    assert put.body == {
        "app_id": "demo",
        "role": "analyst",
        "consent_version": "1",
        "research_consent": True,
        "opt_outs": ["pointer", "interaction"],
        "pointer_device": "touchpad",
    }
    parsed = datetime.fromisoformat(consent_at)
    assert parsed.tzinfo is not None
    assert abs(datetime.now(timezone.utc) - parsed) < timedelta(minutes=1)


def test_all_channels_ticked_gives_empty_opt_outs(logged_in, collector):
    body = {
        "version": "1",
        "channels": {"keystroke": True, "pointer": True, "interaction": True},
        "research_consent": False,
        "pointer_device": "mouse",
    }
    assert logged_in.post("/api/consent", json=body).status_code == 200
    put = collector.calls("PUT", USER_PATH)[0]
    assert put.body["opt_outs"] == []
    assert put.body["research_consent"] is False
    assert put.body["pointer_device"] == "mouse"


def test_only_keystroke_unticked_gives_keystroke_opt_out(logged_in, collector):
    body = dict(CONSENT_BODY, channels={"keystroke": False, "pointer": True, "interaction": True})
    logged_in.post("/api/consent", json=body)
    assert collector.calls("PUT", USER_PATH)[0].body["opt_outs"] == ["keystroke"]


def test_consent_is_sent_to_configured_collector_url(logged_in, collector):
    logged_in.post("/api/consent", json=CONSENT_BODY)
    assert collector.requests[0].headers["host"] == "collector.test:8000"


def test_forwarded_consent_never_contains_username_or_password(logged_in, collector):
    logged_in.post("/api/consent", json=CONSENT_BODY)
    put = collector.calls("PUT", USER_PATH)[0]
    assert "alice" not in str(put.body) and "alice" not in put.path
    assert PASSWORD not in str(put.body)


def test_me_shows_stored_consent(logged_in):
    logged_in.post("/api/consent", json=CONSENT_BODY)
    consent = logged_in.get("/api/me").json()["consent"]
    at = consent.pop("at")
    assert consent == {
        "version": "1",
        "channels": {"keystroke": True, "pointer": False, "interaction": False},
        "research_consent": True,
        "pointer_device": "touchpad",
    }
    assert datetime.fromisoformat(at).tzinfo is not None


def test_login_after_consent_does_not_need_consent(logged_in):
    logged_in.post("/api/consent", json=CONSENT_BODY)
    assert login(logged_in).json()["needs_consent"] is False


def test_changing_consent_forwards_a_new_put(consented, collector):
    body = dict(CONSENT_BODY, channels={"keystroke": True, "pointer": True, "interaction": True})
    assert consented.post("/api/consent", json=body).status_code == 200
    puts = collector.calls("PUT", USER_PATH)
    assert len(puts) == 2
    assert puts[1].body["opt_outs"] == []
    assert consented.get("/api/me").json()["consent"]["channels"]["pointer"] is True


def test_consent_rejected_by_collector_is_not_stored(logged_in, collector):
    collector.fail_with = 503
    response = logged_in.post("/api/consent", json=CONSENT_BODY)
    assert response.status_code == 502
    assert response.json() == {"error": "authwho_unavailable"}
    assert logged_in.get("/api/me").json()["consent"] is None


def test_consent_with_collector_unreachable_returns_502(logged_in, collector):
    collector.unreachable = True
    assert logged_in.post("/api/consent", json=CONSENT_BODY).status_code == 502
    assert logged_in.get("/api/me").json()["consent"] is None


def test_invalid_pointer_device_is_rejected_and_not_forwarded(logged_in, collector):
    body = dict(CONSENT_BODY, pointer_device="trackball")
    assert logged_in.post("/api/consent", json=body).status_code == 422
    assert collector.requests == []


def test_withdrawal_forwards_delete_and_clears_consent(consented, collector, db_path):
    response = consented.delete("/api/consent")
    assert response.status_code == 204
    deletes = collector.calls("DELETE", USER_PATH)
    assert len(deletes) == 1
    assert deletes[0].path == f"/v1/users/{_authwho_user_id(db_path)}"
    assert deletes[0].headers["X-AuthWho-App-Key"] == APP_KEY
    assert consented.get("/api/me").json()["consent"] is None
    assert login(consented).json()["needs_consent"] is True


def test_withdrawal_clears_consent_locally_even_if_collector_fails(consented, collector):
    collector.fail_with = 503
    response = consented.delete("/api/consent")
    assert response.status_code == 502
    assert consented.get("/api/me").json()["consent"] is None


def test_withdrawal_can_be_retried_after_collector_failure(consented, collector):
    collector.fail_with = 503
    consented.delete("/api/consent")
    collector.fail_with = None
    assert consented.delete("/api/consent").status_code == 204
    assert len(collector.calls("DELETE", USER_PATH)) == 2
