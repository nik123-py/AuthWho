"""D1: registration and login with scrypt-hashed passwords."""

import sqlite3

from .conftest import PASSWORD, login, register


def test_register_returns_201_with_username(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json() == {"username": "alice"}


def test_register_creates_database_and_parent_folders(client, db_path):
    register(client)
    assert db_path.is_file()


def test_stored_hash_is_not_the_password(client, db_path):
    register(client)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT password_hash, password_salt FROM users WHERE username = 'alice'"
        ).fetchone()
    stored_hash, salt = row
    assert isinstance(stored_hash, bytes) and len(stored_hash) >= 32
    assert PASSWORD.encode() not in stored_hash
    assert isinstance(salt, bytes) and len(salt) == 16
    assert PASSWORD.encode() not in db_path.read_bytes()


def test_each_user_gets_a_distinct_salt_and_hash_for_the_same_password(client, db_path):
    register(client, "alice")
    register(client, "bob")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT password_hash, password_salt FROM users").fetchall()
    (hash_a, salt_a), (hash_b, salt_b) = rows
    assert salt_a != salt_b
    assert hash_a != hash_b


def test_user_gets_pseudonymous_uuid_and_analyst_role(client, db_path):
    register(client)
    with sqlite3.connect(db_path) as conn:
        authwho_id, role = conn.execute(
            "SELECT authwho_user_id, role FROM users WHERE username = 'alice'"
        ).fetchone()
    assert len(authwho_id) == 36 and authwho_id.count("-") == 4
    assert authwho_id[14] == "4"  # uuid4 version digit
    assert role == "analyst"


def test_duplicate_username_returns_409(client):
    assert register(client).status_code == 201
    response = register(client, password="a different password")
    assert response.status_code == 409


def test_duplicate_username_is_case_insensitive(client):
    register(client, "alice")
    assert register(client, "ALICE").status_code == 409


def test_login_with_correct_password_returns_username_and_needs_consent(client):
    register(client)
    response = login(client)
    assert response.status_code == 200
    assert response.json() == {"username": "alice", "needs_consent": True}


def test_login_with_wrong_password_returns_401(client):
    register(client)
    response = login(client, password="wrong password entirely")
    assert response.status_code == 401
    assert "demo_session" not in response.cookies


def test_login_with_unknown_user_returns_401(client):
    assert login(client, username="nobody").status_code == 401


def test_failed_logins_never_lock_the_account(client):
    register(client)
    for _ in range(20):
        assert login(client, password="wrong password entirely").status_code == 401
    assert login(client).status_code == 200


def test_register_rejects_empty_username_and_short_password(client):
    assert client.post("/api/register", json={"username": "", "password": PASSWORD}).status_code == 422
    assert client.post("/api/register", json={"username": "carol", "password": "short"}).status_code == 422
