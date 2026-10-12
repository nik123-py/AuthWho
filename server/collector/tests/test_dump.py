"""C11: dump tool prints type and category names for a known batch."""

import json

import pytest

from server.collector import dump
from server.common.redis_keys import EVENTS_STREAM
from server.common.testing import redis_url_for_tests

SID = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
STREAM = "33333333-3333-4333-8333-333333333333"


def _fields(session_id, seq, events):
    return {"session_id": session_id, "stream_id": STREAM, "seq": str(seq),
            "received_at": "2026-10-09T12:00:00.000Z", "pointer_device": "mouse",
            "events": json.dumps(events)}


KNOWN = [[1, 1201.3, 1, 0], [2, 1288.9, 1, 0], [1, 1300.0, 4, 1], [3, 1400.0, 10, 20],
         [4, 1450.0, 10, 20, 0], [12, 1500.0, 3]]


def test_text_output_names_types_and_categories():
    out = dump.format_batches([("1-0", _fields(SID, 0, KNOWN))])
    lines = out.splitlines()
    assert lines[0].startswith("batch seq=0 ")
    assert "received_at=2026-10-09T12:00:00.000Z" in lines[0] and "events=6" in lines[0]
    assert lines[1].split() == ["KEY_DOWN", "t=1201.3", "category=letter", "press_id=0"]
    assert lines[2].split()[0:3] == ["KEY_UP", "t=1288.9", "category=letter"]
    assert "category=backspace" in lines[3]
    assert lines[4].split() == ["POINTER_MOVE", "t=1400.0", "x=10", "y=20"]
    assert lines[5].split()[0] == "POINTER_DOWN" and "button=0" in lines[5]
    assert lines[6].split() == ["PAGE", "t=1500.0", "page_code=3"]


def test_json_output_is_structured():
    data = json.loads(dump.format_batches([("1-0", _fields(SID, 4, KNOWN[:2]))], as_json=True))
    assert data == [{
        "seq": 4, "stream_id": STREAM, "received_at": "2026-10-09T12:00:00.000Z", "event_count": 2,
        "events": [
            {"type": "KEY_DOWN", "t": 1201.3, "category": "letter", "press_id": 0},
            {"type": "KEY_UP", "t": 1288.9, "category": "letter", "press_id": 0},
        ],
    }]


@pytest.mark.integration
def test_main_reads_only_the_requested_session(redis_client, monkeypatch, capsys):
    redis_client.xadd(EVENTS_STREAM, _fields(SID, 0, KNOWN[:1]))
    redis_client.xadd(EVENTS_STREAM, _fields(OTHER, 0, KNOWN[3:4]))
    redis_client.xadd(EVENTS_STREAM, _fields(SID, 1, KNOWN[1:2]))
    monkeypatch.setenv("AUTHWHO_REDIS_URL", redis_url_for_tests())
    assert dump.main([SID]) == 0
    out = capsys.readouterr().out
    assert "batch seq=0" in out and "batch seq=1" in out
    assert "KEY_DOWN" in out and "KEY_UP" in out and "POINTER_MOVE" not in out
    assert dump.main([SID, "--json"]) == 0
    assert [b["seq"] for b in json.loads(capsys.readouterr().out)] == [0, 1]


def test_main_rejects_a_non_uuid_session(capsys):
    assert dump.main(["not-a-uuid"]) == 2
