"""End-to-end scenarios in a real browser (Chromium) against the whole stack.

Run from the repository root, with ``docker compose up -d`` first::

    .venv/Scripts/python -m pytest tests/e2e -m e2e

1. The SDK captures events in a real browser and no event contains a typed character.
2. The collector accepts a signed batch and rejects a replayed or tampered one.
3. A takeover lowers trust; a high-risk action then needs a step-up, which a
   genuine user passes and an impostor fails, ending the session.
4. A session with scrolling only is judged with insufficient signal, not a low score.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid

import httpx
import pytest

from tests.e2e.conftest import (
    PASSWORD, human_type, latest_session, register_and_consent, unique_user, wait_for,
)

pytestmark = pytest.mark.e2e

TYPED = "the quick brown fox"


def _events_for(rds, session_id: str) -> list[dict]:
    return [f for _id, f in rds.xrange("aw:events") if f.get("session_id") == session_id]


def test_capture_in_a_real_browser_contains_no_characters(stack, page, db, rds):
    user = unique_user()
    register_and_consent(page, stack["web"], user)
    page.get_by_role("link", name="Write", exact=True).click()
    page.get_by_label("Your note").click()
    human_type(page, len(TYPED), 80, 90, seed=1)
    _, sid = latest_session(stack, db, user)
    entries = wait_for(lambda: _events_for(rds, sid), seconds=20)
    events = [e for f in entries for e in json.loads(f["events"])]
    assert any(e[0] == 1 for e in events), "key-down events were captured"
    assert all(isinstance(v, (int, float)) for e in events for v in e)
    raw = json.dumps(entries)
    for word in TYPED.split():
        assert word not in raw
    assert PASSWORD not in raw


def test_collector_accepts_signed_batches_and_rejects_replays(stack):
    demo = httpx.Client(base_url=stack["demo"], timeout=30)
    user = unique_user()
    demo.post("/api/register", json={"username": user, "password": PASSWORD})
    demo.post("/api/login", json={"username": user, "password": PASSWORD})
    demo.post("/api/consent", json={"version": "1", "channels": {"keystroke": True, "pointer": True,
               "interaction": True}, "research_consent": False, "pointer_device": "mouse"})
    s = demo.post("/api/authwho/stream").json()
    key = base64.urlsafe_b64decode(s["stream_key"] + "=" * (-len(s["stream_key"]) % 4))

    def send(seq: int, nonce: str, tamper: bool = False) -> httpx.Response:
        body = json.dumps({"v": 1, "session_id": s["session_id"], "stream_id": s["stream_id"], "seq": seq,
                           "nonce": nonce, "sent_at": 10.0, "pointer_device": "mouse",
                           "events": [[1, 1.0, 1, 0], [2, 80.0, 1, 0]]}).encode()
        sig = base64.urlsafe_b64encode(hmac.new(key, body, hashlib.sha256).digest()).rstrip(b"=").decode()
        if tamper:
            body = body.replace(b"80.0", b"81.0")
        return httpx.post(f"{stack['api']}/v1/batches", content=body,
                          headers={"Content-Type": "application/json", "X-AuthWho-Signature": sig})

    nonce = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
    assert send(0, nonce).status_code == 202
    replay = send(0, nonce)
    assert replay.status_code == 409 and replay.json()["error"] == "replay"
    assert send(1, base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode(), tamper=True).status_code == 401


def _enrol_then_take_over(stack, page, db) -> tuple[str, str]:
    user = unique_user()
    register_and_consent(page, stack["web"], user)
    page.get_by_role("link", name="Write", exact=True).click()
    page.get_by_label("Your note").click()
    human_type(page, 180, hold_ms=80, gap_ms=90, seed=2)  # enrolment (5 windows) and a few scored windows
    _, sid = latest_session(stack, db, user)
    first = wait_for(lambda: db.execute(
        "SELECT trust FROM trust_points WHERE session_id = %s AND state = 'scored' ORDER BY seq DESC LIMIT 1",
        (sid,)).fetchone(), seconds=60)
    assert first[0] >= 75, "the enrolled typist is trusted"

    def low_trust():
        row = db.execute("SELECT trust FROM trust_points WHERE session_id = %s AND state = 'scored' "
                         "ORDER BY seq DESC LIMIT 1", (sid,)).fetchone()
        return row is not None and row[0] < 75

    for chunk in range(10):  # someone else, with a much slower rhythm and longer key holds
        human_type(page, 25, hold_ms=190, gap_ms=260, seed=100 + chunk)
        if low_trust():
            break
    wait_for(low_trust, seconds=30)
    return user, sid


def _try_payee(page) -> None:
    page.get_by_role("link", name="Payees", exact=True).click()
    page.get_by_label("Payee name").fill("Ravi")
    page.get_by_label("Account number").fill("12345")
    page.get_by_role("button", name="Add payee").click()


def test_takeover_step_up_passed_by_the_genuine_user(stack, page, db):
    _user, sid = _enrol_then_take_over(stack, page, db)
    _try_payee(page)
    dialog = page.get_by_role("dialog", name="Confirm it is you")
    dialog.wait_for()
    dialog.get_by_label("Password").fill(PASSWORD)
    dialog.get_by_role("button", name="Confirm").click()
    dialog.wait_for(state="detached")
    page.get_by_role("button", name="Add payee").click()
    page.get_by_text("Payee added").wait_for()
    rows = db.execute("SELECT trigger, outcome, step_up_result, explanation FROM decisions WHERE session_id = %s "
                      "ORDER BY created_at", (sid,)).fetchall()
    assert ("action_request", "step_up") in [(r[0], r[1]) for r in rows]
    assert any(r[2] == "passed" for r in rows)
    assert all(r[3] and r[3].endswith(".") for r in rows)


def test_takeover_failed_step_up_ends_the_session(stack, page, db):
    _user, sid = _enrol_then_take_over(stack, page, db)
    _try_payee(page)
    dialog = page.get_by_role("dialog", name="Confirm it is you")
    dialog.wait_for()
    for attempt in range(3):
        dialog.get_by_label("Password").fill("not the password")
        dialog.get_by_role("button", name="Confirm").click()
        if attempt < 2:
            dialog.get_by_text("attempt").wait_for()
    page.get_by_role("heading", name="Your session has ended").wait_for()
    row = db.execute("SELECT level, outcome, explanation FROM decisions WHERE session_id = %s "
                     "AND step_up_result = 'failed'", (sid,)).fetchone()
    assert row[0] == "critical" and row[1] == "terminate" and "identity check failed" in row[2]
    assert db.execute("SELECT status FROM sessions WHERE session_id = %s", (sid,)).fetchone()[0] == "terminated"


def test_scrolling_only_is_insufficient_signal(stack, page, db):
    user = unique_user()
    register_and_consent(page, stack["web"], user)
    page.get_by_role("link", name="Payees", exact=True).click()
    for _ in range(15):
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(100)
    page.get_by_label("Payee name").fill("Ravi")
    page.get_by_label("Account number").fill("12345")
    page.get_by_role("button", name="Add payee").click()
    page.get_by_text("Payee added").wait_for()
    _, sid = latest_session(stack, db, user)
    row = db.execute("SELECT level, outcome, action_allowed, trust FROM decisions WHERE session_id = %s "
                     "AND trigger = 'action_request'", (sid,)).fetchone()
    assert row == ("insufficient_signal", "continue", True, None)
