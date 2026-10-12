"""D9: a consent withdrawal that AuthWho could not complete is retried until it is.

Capture stops locally at once, a durable ``withdrawal_pending`` flag is kept in
the demo database, and the DELETE is retried on login, GET /api/me and
POST /api/consent until AuthWho answers 204 (or 404, already gone).
"""

import sqlite3

from .conftest import CONSENT_BODY, PASSWORD, login, register

USER_PATH = r"/v1/users/[0-9a-f-]{36}"


def _deletes(collector) -> int:
    return len(collector.calls("DELETE", USER_PATH))


def _withdraw_while_authwho_down(client, collector):
    collector.fail_with = 502
    response = client.delete("/api/consent")
    assert response.status_code == 502
    assert response.json() == {"error": "authwho_unavailable"}
    return response


def test_successful_withdrawal_is_not_pending(consented):
    assert consented.delete("/api/consent").status_code == 204
    me = consented.get("/api/me").json()
    assert me["consent"] is None
    assert me["withdrawal_pending"] is False


def test_me_reports_no_pending_withdrawal_for_new_user(logged_in):
    assert logged_in.get("/api/me").json() == {
        "username": "alice",
        "consent": None,
        "withdrawal_pending": False,
    }


def test_failed_withdrawal_stops_capture_and_is_pending(consented, collector):
    _withdraw_while_authwho_down(consented, collector)
    me = consented.get("/api/me").json()
    assert me["consent"] is None
    assert me["withdrawal_pending"] is True


def test_reload_with_authwho_healthy_completes_the_deletion(consented, collector):
    _withdraw_while_authwho_down(consented, collector)
    collector.fail_with = None

    me = consented.get("/api/me").json()

    assert _deletes(collector) == 2
    assert me["withdrawal_pending"] is False
    consented.get("/api/me")
    assert _deletes(collector) == 2  # flag cleared, so no further retries


def test_me_keeps_flag_while_authwho_stays_down(consented, collector):
    _withdraw_while_authwho_down(consented, collector)
    assert consented.get("/api/me").json()["withdrawal_pending"] is True
    assert _deletes(collector) == 2  # retried on GET /api/me, failed again


def test_404_from_authwho_counts_as_already_deleted(consented, collector):
    _withdraw_while_authwho_down(consented, collector)
    collector.fail_with = None
    collector.user_delete_status = 404
    assert consented.get("/api/me").json()["withdrawal_pending"] is False


def test_other_errors_keep_the_withdrawal_pending(consented, collector):
    _withdraw_while_authwho_down(consented, collector)
    collector.fail_with = None
    collector.user_delete_status = 500
    assert consented.get("/api/me").json()["withdrawal_pending"] is True


def test_login_retries_the_pending_deletion(consented, collector):
    _withdraw_while_authwho_down(consented, collector)
    collector.fail_with = None
    response = login(consented)
    assert response.status_code == 200
    assert response.json() == {"username": "alice", "needs_consent": True}
    assert _deletes(collector) == 2
    assert consented.get("/api/me").json()["withdrawal_pending"] is False
    assert _deletes(collector) == 2


def test_login_succeeds_while_authwho_is_down_and_flag_stays(consented, collector):
    _withdraw_while_authwho_down(consented, collector)
    response = login(consented)
    assert response.status_code == 200
    assert response.json()["needs_consent"] is True
    assert consented.get("/api/me").json()["withdrawal_pending"] is True


def test_no_stream_can_be_minted_while_withdrawal_is_pending(consented, collector):
    consented.post("/api/authwho/stream")
    _withdraw_while_authwho_down(consented, collector)
    collector.fail_with = None
    before = len(collector.requests)

    response = consented.post("/api/authwho/stream")

    assert response.status_code == 409
    assert response.json() == {"error": "no_consent"}
    minted = [r for r in collector.requests[before:] if r.path.startswith("/v1/sessions")]
    assert minted == []


def test_new_consent_first_completes_the_pending_deletion(consented, collector):
    _withdraw_while_authwho_down(consented, collector)
    collector.fail_with = None
    before = len(collector.requests)

    assert consented.post("/api/consent", json=CONSENT_BODY).status_code == 200

    sent = [(r.method, r.path.split("/")[2]) for r in collector.requests[before:]]
    assert sent == [("DELETE", "users"), ("PUT", "users")]
    me = consented.get("/api/me").json()
    assert me["withdrawal_pending"] is False
    assert me["consent"] is not None


def test_new_consent_fails_with_502_while_deletion_cannot_complete(consented, collector):
    _withdraw_while_authwho_down(consented, collector)
    collector.fail_with = None
    collector.user_delete_status = 500

    response = consented.post("/api/consent", json=CONSENT_BODY)

    assert response.status_code == 502
    assert response.json() == {"error": "authwho_unavailable"}
    assert collector.calls("PUT", USER_PATH)[1:] == []  # only the original consent PUT
    me = consented.get("/api/me").json()
    assert me["consent"] is None
    assert me["withdrawal_pending"] is True


def test_pending_withdrawal_survives_an_app_restart(consented, collector, make_client):
    _withdraw_while_authwho_down(consented, collector)

    restarted = make_client()
    assert login(restarted).status_code == 200  # AuthWho still down
    assert restarted.get("/api/me").json()["withdrawal_pending"] is True

    collector.fail_with = None
    assert restarted.get("/api/me").json()["withdrawal_pending"] is False
    assert collector.calls("DELETE", USER_PATH)[-1].path == collector.calls("DELETE", USER_PATH)[0].path


def test_database_created_before_the_flag_existed_is_upgraded(db_path, make_client):
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash BLOB NOT NULL,
                password_salt BLOB NOT NULL,
                authwho_user_id TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consent_version TEXT,
                consent_at TEXT,
                research_consent INTEGER,
                channel_keystroke INTEGER,
                channel_pointer INTEGER,
                channel_interaction INTEGER,
                pointer_device TEXT
            );
            CREATE TABLE login_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                authwho_session_id TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
    client = make_client()
    assert register(client).status_code == 201
    assert login(client, password=PASSWORD).status_code == 200
    assert client.get("/api/me").json()["withdrawal_pending"] is False
