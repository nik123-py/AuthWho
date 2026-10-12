"""D5 notes, D6 registry and D7 high-risk actions."""

import logging

NOTE_TEXT = "Meeting with Priya about the zebra-quartz-7731 budget"


# D5: free-text notes are discarded


def test_notes_returns_204_with_empty_body(logged_in):
    response = logged_in.post("/api/notes", json={"text": NOTE_TEXT})
    assert response.status_code == 204
    assert response.content == b""


def test_note_text_is_never_stored_logged_or_forwarded(logged_in, collector, db_path, caplog):
    caplog.set_level(logging.DEBUG)
    assert logged_in.post("/api/notes", json={"text": NOTE_TEXT}).status_code == 204

    for path in db_path.parent.iterdir():
        assert b"zebra-quartz-7731" not in path.read_bytes(), path.name
    assert "zebra-quartz-7731" not in caplog.text
    assert collector.requests == []


def test_note_without_text_field_is_rejected(logged_in):
    assert logged_in.post("/api/notes", json={}).status_code == 422


# D6: page and action registry


def test_registry_matches_section_15_exactly(client):
    response = client.get("/api/registry")
    assert response.status_code == 200
    assert response.json() == {
        "pages": {
            "home": 1,
            "write": 2,
            "form": 3,
            "payees": 4,
            "reports": 5,
            "collect": 6,
            "settings": 7,
        },
        "actions": {"add_payee": 1, "export_report": 2},
    }


# D7: high-risk actions (policy checks arrive in P4)


def test_add_payee_when_logged_in_returns_ok(logged_in):
    response = logged_in.post("/api/payees", json={"name": "Bob Example", "account": "12345678"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_add_payee_requires_name_and_account(logged_in):
    assert logged_in.post("/api/payees", json={"name": "Bob Example"}).status_code == 422
    assert logged_in.post("/api/payees", json={"account": "12345678"}).status_code == 422


def test_export_report_when_logged_in_returns_ok(logged_in):
    response = logged_in.post("/api/reports/export")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_high_risk_actions_after_logout_return_401(logged_in):
    logged_in.post("/api/logout")
    assert logged_in.post("/api/payees", json={"name": "Bob", "account": "1"}).status_code == 401
    assert logged_in.post("/api/reports/export").status_code == 401
