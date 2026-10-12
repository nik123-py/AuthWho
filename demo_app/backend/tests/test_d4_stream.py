"""D4: AuthWho session and stream minting, and session end on logout."""

import sqlite3

from .conftest import APP_KEY, COLLECTOR_URL, CONSENT_BODY, login

SESSIONS = r"/v1/sessions"
STREAMS = r"/v1/sessions/[0-9a-f-]{36}/streams"
END = r"/v1/sessions/[0-9a-f-]{36}/end"


def _authwho_user_id(db_path) -> str:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT authwho_user_id FROM users WHERE username = 'alice'").fetchone()[0]


def test_stream_before_consent_returns_409_and_calls_nothing(logged_in, collector):
    response = logged_in.post("/api/authwho/stream")
    assert response.status_code == 409
    assert response.json() == {"error": "no_consent"}
    assert collector.requests == []


def test_stream_after_consent_returns_section_15_payload(consented, collector):
    response = consented.post("/api/authwho/stream")
    assert response.status_code == 200
    assert response.json() == {
        "endpoint": COLLECTOR_URL,
        "session_id": collector.session_ids[0],
        "stream_id": collector.stream_ids[0],
        "stream_key": "q83vEjRWeJq83vEjRWeJq83vEjRWeJq83vEjRWeJq80",
        "channels": {"keystroke": True, "pointer": False, "interaction": True},
        "pointer_device": "touchpad",
    }


def test_stream_response_is_not_cached(consented):
    assert consented.post("/api/authwho/stream").headers["cache-control"] == "no-store"


def test_session_is_created_with_pseudonymous_id_only(consented, collector, db_path):
    consented.post("/api/authwho/stream")
    created = collector.calls("POST", SESSIONS)
    assert len(created) == 1
    assert created[0].body == {"user_id": _authwho_user_id(db_path), "app_id": "demo", "role": "analyst"}
    assert created[0].headers["X-AuthWho-App-Key"] == APP_KEY


def test_session_created_once_per_login_and_stream_per_call(consented, collector):
    first = consented.post("/api/authwho/stream").json()
    second = consented.post("/api/authwho/stream").json()
    third = consented.post("/api/authwho/stream").json()

    assert len(collector.calls("POST", SESSIONS)) == 1
    streams = collector.calls("POST", STREAMS)
    assert len(streams) == 3
    assert {s.path for s in streams} == {f"/v1/sessions/{first['session_id']}/streams"}
    assert all(s.headers["X-AuthWho-App-Key"] == APP_KEY for s in streams)
    assert first["session_id"] == second["session_id"] == third["session_id"]
    assert len({first["stream_id"], second["stream_id"], third["stream_id"]}) == 3


def test_new_login_creates_a_new_authwho_session(consented, collector):
    first = consented.post("/api/authwho/stream").json()["session_id"]
    login(consented)
    second = consented.post("/api/authwho/stream").json()["session_id"]
    assert first != second
    assert len(collector.calls("POST", SESSIONS)) == 2


def test_stream_after_withdrawal_returns_409(consented, collector):
    consented.post("/api/authwho/stream")
    consented.delete("/api/consent")
    response = consented.post("/api/authwho/stream")
    assert response.status_code == 409
    assert response.json() == {"error": "no_consent"}


def test_consent_again_after_withdrawal_creates_a_fresh_session(consented, collector):
    first = consented.post("/api/authwho/stream").json()["session_id"]
    consented.delete("/api/consent")
    consented.post("/api/consent", json=CONSENT_BODY)
    second = consented.post("/api/authwho/stream").json()["session_id"]
    assert first != second


def test_collector_without_consent_row_maps_to_409(consented, collector):
    collector.consented_users.clear()
    response = consented.post("/api/authwho/stream")
    assert response.status_code == 409
    assert response.json() == {"error": "no_consent"}


def test_collector_failure_returns_502(consented, collector):
    collector.fail_with = 500
    response = consented.post("/api/authwho/stream")
    assert response.status_code == 502
    assert response.json() == {"error": "authwho_unavailable"}


def test_failed_session_creation_is_retried_on_next_call(consented, collector):
    collector.unreachable = True
    assert consented.post("/api/authwho/stream").status_code == 502
    collector.unreachable = False
    assert consented.post("/api/authwho/stream").status_code == 200


def test_logout_ends_the_authwho_session(consented, collector):
    session_id = consented.post("/api/authwho/stream").json()["session_id"]
    assert consented.post("/api/logout").status_code == 204
    ends = collector.calls("POST", END)
    assert len(ends) == 1
    assert ends[0].path == f"/v1/sessions/{session_id}/end"
    assert ends[0].body == {"reason": "logout"}
    assert ends[0].headers["X-AuthWho-App-Key"] == APP_KEY


def test_logout_without_authwho_session_calls_nothing(logged_in, collector):
    assert logged_in.post("/api/logout").status_code == 204
    assert collector.requests == []


def test_logout_succeeds_even_if_collector_is_down(consented, collector):
    consented.post("/api/authwho/stream")
    token = consented.cookies["demo_session"]
    collector.unreachable = True
    assert consented.post("/api/logout").status_code == 204
    consented.cookies.set("demo_session", token)
    assert consented.get("/api/me").status_code == 401
